import {
  Users,
  BarChart3,
  Settings as SettingsIcon,
  CreditCard,
  HelpCircle,
  TrendingUp,
  Play,
  Bug,
  MessageSquare,
  Database,
  Headphones,
  Ticket,
  Gift,
} from "lucide-react";

/**
 * Navigation items for the admin dashboard sidebar
 * Each item includes an id, label, and icon component
 */
export const navigationItems = [
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
  { id: "promo-codes", label: "Promo Codes", icon: Ticket },
  { id: "referrals", label: "Referrals", icon: Gift },
  { id: "help", label: "Help & Docs", icon: HelpCircle },
];
