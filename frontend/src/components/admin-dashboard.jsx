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
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
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
  Trash,
  Bug,
  Mail,
  MailCheck,
  ArrowLeft,
  Coins,
} from "lucide-react";
import React, { useState, useEffect } from "react";
import { useAuth } from "@/AuthContext";
import { makeApi, buildApiUrl } from "@/lib/apiClient";
import DbExplorer from '@/components/admin/DbExplorer.jsx';
import { useToast } from '@/hooks/use-toast';
import AdminFeatureToggles from '@/components/admin/AdminFeatureToggles.jsx';
import AdminLayoutToggle from '@/components/admin/AdminLayoutToggle.jsx';
import AdminTierEditor from '@/components/admin/AdminTierEditor.jsx';
import AdminTierEditorV2 from '@/components/admin/AdminTierEditorV2.jsx';
import AdminMusicLibrary from '@/components/admin/AdminMusicLibrary.jsx';
import AdminLandingEditor from '@/components/admin/AdminLandingEditor.jsx';
import AdminBugsTab from '@/components/admin/tabs/AdminBugsTab.jsx';
import AdminPodcastsTab from '@/components/admin/tabs/AdminPodcastsTab.jsx';
import AdminBillingTab from '@/components/admin/tabs/AdminBillingTab.jsx';
import AdminHelpTab from '@/components/admin/tabs/AdminHelpTab.jsx';
import { useResolvedTimezone } from '@/hooks/useResolvedTimezone';
import { formatInTimezone } from '@/lib/timezone';

export default function AdminDashboard() {
  const { token, logout, user: authUser } = useAuth();
  const { toast } = useToast();
  const resolvedTimezone = useResolvedTimezone();
  
  // Determine admin role (superadmin has full access, admin has restrictions)
  const userRole = authUser?.role?.toLowerCase() || (authUser?.is_admin ? 'admin' : 'user');
  const isSuperAdmin = userRole === 'superadmin';
  const isAdmin = userRole === 'admin' || isSuperAdmin;
  
  // Check for ?tab= query parameter to auto-navigate to specific tab
  const urlParams = new URLSearchParams(window.location.search);
  const initialTab = urlParams.get('tab') || 'users';
  const [activeTab, setActiveTab] = useState(initialTab)
  const [searchTerm, setSearchTerm] = useState("")
  const [tierFilter, setTierFilter] = useState("all")
  const [statusFilter, setStatusFilter] = useState("all")
  const [verificationFilter, setVerificationFilter] = useState("all")  // NEW: Email verification filter
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
    { id: "bugs", label: "Bug Reports", icon: Bug },
    { id: "tiers", label: "Tier Editor", icon: SettingsIcon },
    { id: "music", label: "Music Library", icon: Headphones },
    { id: "landing", label: "Front Page Content", icon: MessageSquare },
    { id: "db", label: "DB Explorer", icon: Database },
    { id: "settings", label: "Settings", icon: SettingsIcon },
    { id: "billing", label: "Billing", icon: CreditCard },
    { id: "help", label: "Help & Docs", icon: HelpCircle },
  ]

  // Filter users based on search + tier + status + verification
  const filteredUsers = users.filter((user) => {
    const q = searchTerm.trim().toLowerCase();
    const email = (user.email || '').toLowerCase();
    const tier = (user.tier || '').toLowerCase();
    const matchesSearch = !q || email.includes(q) || tier.includes(q);
    const matchesTier = (tierFilter === 'all') || (tier === tierFilter);
    const matchesStatus = (statusFilter === 'all')
      || (statusFilter === 'active' && !!user.is_active)
      || ((statusFilter === 'inactive' || statusFilter === 'suspended') && !user.is_active);
    const matchesVerification = (verificationFilter === 'all')
      || (verificationFilter === 'verified' && !!user.email_verified)
      || (verificationFilter === 'unverified' && !user.email_verified);
    return matchesSearch && matchesTier && matchesStatus && matchesVerification;
  })

  const [savingIds, setSavingIds] = useState(new Set());
  const [saveErrors, setSaveErrors] = useState({});
  // Local edit buffer for date inputs so we don't PATCH on every keystroke
  const [editingDates, setEditingDates] = useState({});
  
  // Admin tier confirmation dialog state
  const [adminTierDialog, setAdminTierDialog] = useState({ open: false, userId: null, userName: '', confirmText: '' });
  
  // Credit viewer dialog state
  const [creditViewerDialog, setCreditViewerDialog] = useState({ open: false, userId: null, userData: null, loading: false });

  const updateUser = async (id, payload) => {
    // Special handling for admin tier assignment - requires confirmation
    if (payload.tier === 'admin') {
      const targetUser = users.find(u => u.id === id);
      if (!targetUser) return;
      
      setAdminTierDialog({
        open: true,
        userId: id,
        userName: targetUser.email || 'this user',
        confirmText: ''
      });
      return; // Will complete after dialog confirmation
    }
    
    setSavingIds(prev => new Set([...prev, id]));
    setSaveErrors(e => ({...e, [id]: null}));
    try {
      const api = makeApi(token);
      const updated = await api.patch(`/api/admin/users/${id}`, payload);
      setUsers(u => u.map(x => x.id === id ? updated : x));
      
      // Show success message for admin tier changes
      if (payload.tier && payload.tier !== 'admin') {
        try { toast({ title: 'Tier updated', description: `User tier changed to ${payload.tier}` }); } catch {}
      }
    } catch(e) {
      setSaveErrors(errs => ({...errs, [id]: e.message || 'Network error'}));
      toastApiError(e, 'Failed to update user');
    } finally {
      setSavingIds(prev => { const n = new Set(prev); n.delete(id); return n; });
    }
  }
  
  const confirmAdminTier = async () => {
    if (adminTierDialog.confirmText.toLowerCase() !== 'yes') {
      try { toast({ title: 'Confirmation required', description: 'You must type "yes" to confirm', variant: 'destructive' }); } catch {}
      return;
    }
    
    const { userId } = adminTierDialog;
    setAdminTierDialog({ open: false, userId: null, userName: '', confirmText: '' });
    
    setSavingIds(prev => new Set([...prev, userId]));
    setSaveErrors(e => ({...e, [userId]: null}));
    try {
      const api = makeApi(token);
      const updated = await api.patch(`/api/admin/users/${userId}`, { tier: 'admin' });
      setUsers(u => u.map(x => x.id === userId ? updated : x));
      try { toast({ title: 'Admin access granted', description: 'User has been granted admin privileges' }); } catch {}
    } catch(e) {
      setSaveErrors(errs => ({...errs, [userId]: e.message || 'Network error'}));
      toastApiError(e, 'Failed to grant admin access');
    } finally {
      setSavingIds(prev => { const n = new Set(prev); n.delete(userId); return n; });
    }
  }
  
  const viewUserCredits = async (userId) => {
    setCreditViewerDialog({ open: true, userId, userData: null, loading: true });
    
    try {
      const api = makeApi(token);
      const data = await api.get(`/api/admin/users/${userId}/credits`);
      setCreditViewerDialog(prev => ({ ...prev, userData: data, loading: false }));
    } catch(e) {
      toastApiError(e, 'Failed to load credit data');
      setCreditViewerDialog({ open: false, userId: null, userData: null, loading: false });
    }
  }

  const prepareUserForDeletion = async (userId, userEmail, userIsActive, userTier) => {
    // Check if user needs to be prepared (set to inactive + free tier)
    const needsPrep = userIsActive || (userTier && userTier.toLowerCase() !== 'free');
    
    if (!needsPrep) {
      // User is already inactive and free tier, proceed with deletion
      deleteUser(userId, userEmail, false);
      return;
    }
    
    // Show warning that user needs to be prepared first
    const prepConfirm = window.confirm(
      `⚠️ SAFETY CHECK: This user must be INACTIVE and on FREE tier before deletion.\n\n` +
      `User: ${userEmail}\n` +
      `Current Status: ${userIsActive ? 'ACTIVE' : 'INACTIVE'}\n` +
      `Current Tier: ${userTier || 'unknown'}\n\n` +
      `Click OK to automatically set this user to INACTIVE + FREE tier, then you can delete them.\n` +
      `Click Cancel to abort.`
    );
    
    if (!prepConfirm) {
      return; // User cancelled
    }
    
    setSavingIds(prev => new Set([...prev, userId]));
    try {
      const api = makeApi(token);
      
      // Set user to inactive + free tier
      const payload = {
        is_active: false,
        tier: 'free'
      };
      
      await api.patch(`/api/admin/users/${userId}`, payload);
      
      // Update local state
      setUsers(prev => prev.map(u => u.id === userId ? { ...u, is_active: false, tier: 'free' } : u));
      
      try {
        toast({
          title: 'User prepared for deletion',
          description: `${userEmail} is now INACTIVE and on FREE tier. You can now delete this user.`,
        });
      } catch {}
      
    } catch (e) {
      toastApiError(e, 'Failed to prepare user for deletion');
    } finally {
      setSavingIds(prev => { const n = new Set(prev); n.delete(userId); return n; });
    }
  };

  const deleteUser = async (userId, userEmail, showPrep = true) => {
    const confirmation = window.prompt(
      `⚠️ WARNING: This will PERMANENTLY delete this user and ALL their data!\n\n` +
      `User: ${userEmail}\n\n` +
      `This includes:\n` +
      `• User account\n` +
      `• All podcasts\n` +
      `• All episodes\n` +
      `• All media items\n\n` +
      `Type "yes" to confirm deletion:`
    );

    if (!confirmation) {
      return; // User cancelled
    }

    if (confirmation.toLowerCase() !== 'yes') {
      try {
        toast({
          title: 'Confirmation failed',
          description: `Please type "yes" to confirm deletion.`,
          variant: 'destructive'
        });
      } catch {}
      return;
    }

    setSavingIds(prev => new Set([...prev, userId]));
    try {
      const api = makeApi(token);
      console.log('[DEBUG] Deleting user:', userId, 'Email:', userEmail);
      console.log('[DEBUG] Request URL:', `/api/admin/users/${userId}`);
      console.log('[DEBUG] Request body:', { confirm_email: userEmail });
      const result = await api.del(`/api/admin/users/${userId}`, { confirm_email: userEmail });
      console.log('[DEBUG] Delete successful:', result);
      
      // Remove user from the list
      setUsers(u => u.filter(x => x.id !== userId));
      
      // Refresh summary and metrics to reflect deleted data
      api.get('/api/admin/summary')
        .then((d) => setSummary(d))
        .catch((e) => { /* silently fail, not critical */ });
      
      // Show success message with GCS cleanup info
      const gcsCommand = result?.gcs_cleanup_command;
      try {
        toast({
          title: 'User deleted',
          description: gcsCommand 
            ? `User deleted. GCS files may need manual cleanup. Check console for command.`
            : 'User and all associated data deleted successfully.',
        });
      } catch {}
      
      // Log the full result for admin reference with GCS cleanup command
      console.log('[ADMIN] User deletion result:', result);
      if (gcsCommand) {
        console.log('[ADMIN] GCS Cleanup Command:', gcsCommand);
      }
      
    } catch(e) {
      console.error('[DEBUG] Delete failed:', e);
      console.error('[DEBUG] Error status:', e?.status);
      console.error('[DEBUG] Error detail:', e?.detail);
      console.error('[DEBUG] Error message:', e?.message);
      console.error('[DEBUG] Error object full:', JSON.stringify(e, null, 2));
      // Check if error is about safety guardrails
      const errorDetail = e?.detail || e?.message || e?.error?.detail || '';
      const isSafetyError = errorDetail.includes('inactive') || errorDetail.includes('free tier');
      
      if (isSafetyError && showPrep) {
        // Offer to prepare user for deletion
        try {
          toast({
            title: 'Safety check failed',
            description: errorDetail + ' Use the "Prepare for Deletion" button first.',
            variant: 'destructive',
            duration: 6000,
          });
        } catch {}
      } else {
        toastApiError(e, 'Failed to delete user');
      }
    } finally {
      setSavingIds(prev => { const n = new Set(prev); n.delete(userId); return n; });
    }
  };

  const verifyUserEmail = async (userId, userEmail) => {
    const confirmed = window.confirm(
      `Manually verify email for ${userEmail}?\n\n` +
      `This will mark their email as verified, allowing them to access the platform.\n\n` +
      `Use this for users who are having trouble with automated verification.`
    );
    
    if (!confirmed) return;
    
    setSavingIds(prev => new Set([...prev, userId]));
    try {
      const api = makeApi(token);
      const result = await api.post(`/api/admin/users/${userId}/verify-email`);
      
      // Update local user state
      setUsers(prev => prev.map(u => 
        u.id === userId ? { ...u, email_verified: true } : u
      ));
      
      try {
        toast({
          title: 'Email verified',
          description: result.already_verified 
            ? `${userEmail} was already verified.`
            : `${userEmail} has been manually verified.`,
        });
      } catch {}
      
      console.log('[ADMIN] Email verification result:', result);
      
    } catch (e) {
      toastApiError(e, 'Failed to verify email');
    } finally {
      setSavingIds(prev => { const n = new Set(prev); n.delete(userId); return n; });
    }
  };

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
  if (t === 'admin') return <Badge className="bg-orange-100 text-orange-800">Admin</Badge>;
  if (t === 'superadmin') return <Badge className="bg-red-100 text-red-800">Super Admin</Badge>;
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
            <Select value={verificationFilter} onValueChange={setVerificationFilter}>
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

              {/* Users Table */}
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
                                  onClick={() => verifyUserEmail(user.id, user.email)}
                                  title="Manually verify this user's email"
                                >
                                  <Mail className="w-3 h-3 mr-1" />
                                  Verify
                                </Button>
                              )}
                            </TableCell>
                            <TableCell>{getTierBadge(user.tier || 'free')}</TableCell>
                            <TableCell>{getStatusBadge(user.is_active ? 'Active' : 'Inactive')}</TableCell>
                            <TableCell className="text-gray-600">{user.episode_count}</TableCell>
                            <TableCell className="text-gray-600">{user.last_activity ? user.last_activity.slice(0,10) : '—'}</TableCell>
                            <TableCell>
                              <div className="flex items-center space-x-2">
                <Select defaultValue={user.tier || 'free'} onValueChange={val => updateUser(user.id,{tier: val})} disabled={savingIds.has(user.id) || (user.tier === 'superadmin')}>
                                  <SelectTrigger className="w-24 h-8 text-xs" aria-label={`Tier for ${displayName}`}><SelectValue /></SelectTrigger>
                                  <SelectContent>
                                    <SelectItem value="free">Free</SelectItem>
                                    <SelectItem value="creator">Creator</SelectItem>
                                    <SelectItem value="pro">Pro</SelectItem>
                  <SelectItem value="unlimited">Unlimited</SelectItem>
                                    {isSuperAdmin && <SelectItem value="admin">Admin</SelectItem>}
                                    {user.tier === 'superadmin' && <SelectItem value="superadmin" disabled>Super Admin</SelectItem>}
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
                                {(user.is_active || (user.tier && user.tier.toLowerCase() !== 'free')) && (
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    className="h-8 px-2 text-[10px] text-orange-600 hover:text-orange-700 hover:bg-orange-50"
                                    disabled={savingIds.has(user.id)}
                                    onClick={() => prepareUserForDeletion(user.id, user.email, user.is_active, user.tier)}
                                    title="Set user to INACTIVE + FREE tier (required before deletion)"
                                  >
                                    Prep
                                  </Button>
                                )}
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="h-8 px-2 text-[10px] text-blue-600 hover:text-blue-700 hover:bg-blue-50"
                                  onClick={() => viewUserCredits(user.id)}
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
                                    onClick={() => prepareUserForDeletion(user.id, user.email, user.is_active, user.tier)}
                                    title={
                                      (user.is_active || (user.tier && user.tier.toLowerCase() !== 'free'))
                                        ? "User must be INACTIVE + FREE tier to delete. Click to prepare first."
                                        : "Delete user and all their data (permanent)"
                                    }
                                    aria-label={`Delete user ${displayName}`}
                                  >
                                    <Trash className="h-4 w-4" />
                                  </Button>
                                )}
                                {!isSuperAdmin && isAdmin && (
                                  <span className="text-[10px] text-gray-500 italic px-2" title="Only superadmin can delete users">Delete restricted</span>
                                )}
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
          {activeTab === 'tiers' && (
            <div className="space-y-4">
              <AdminTierEditorV2 />
              <div className="mt-8 pt-8 border-t">
                <div className="text-sm text-gray-500 mb-4">Legacy Editor (Deprecated)</div>
                <AdminTierEditor />
              </div>
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
                    <AdminFeatureToggles 
                      token={token} 
                      initial={adminSettings} 
                      onSaved={(s)=>setAdminSettings(s)} 
                      readOnly={!isSuperAdmin}
                      allowMaintenanceToggle={true}
                    />
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
      <Dialog open={adminTierDialog.open} onOpenChange={(open) => !open && setAdminTierDialog({ open: false, userId: null, userName: '', confirmText: '' })}>
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
            <Button variant="outline" onClick={() => setAdminTierDialog({ open: false, userId: null, userName: '', confirmText: '' })}>
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
      <Dialog open={creditViewerDialog.open} onOpenChange={(open) => !open && setCreditViewerDialog({ open: false, userId: null, userData: null, loading: false })}>
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
            <Button variant="outline" onClick={() => setCreditViewerDialog({ open: false, userId: null, userData: null, loading: false })}>
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
