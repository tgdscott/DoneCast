
import React from "react";
import { 
  FileText, 
  Mic, 
  Upload, 
  Headphones, 
  Layers, 
  CreditCard, 
  BarChart3, 
  Globe2,
  Settings as SettingsIcon
} from "lucide-react";

export default function SideBar({ collapsed, setCollapsed, onNavigate, active }) {
  const items = [
    { label: "Episodes", icon: FileText, route: "episode-history" },
    { label: "Record", icon: Mic, route: "recorder" },
    { label: "Media Uploads", icon: Upload, route: "media-library" },
    { label: "My Podcasts", icon: Headphones, route: "podcast-manager" },
    { label: "Templates", icon: Layers, route: "my-templates" },
    { label: "Analytics", icon: BarChart3, route: "analytics" },
    { label: "Website Builder", icon: Globe2, route: "website-builder" },
    { label: "Subscription", icon: CreditCard, route: "billing" },
    { label: "Settings", icon: SettingsIcon, route: "settings" },
  ];
  return (
    <aside className={(collapsed ? "w-16 " : "w-64 ") + "shrink-0 border-r bg-card"}>
      <div className="h-16 flex items-center justify-between px-3 border-b">
        <span className={"text-sm font-medium truncate " + (collapsed ? "sr-only" : "")}>Workspace</span>
        <button
          className="size-8 grid place-items-center rounded-lg hover:bg-muted focus:outline-none focus-visible:ring"
          title={collapsed ? "Expand" : "Collapse"}
          onClick={() => setCollapsed((v) => !v)}
        >
          <span aria-hidden="true">≡</span>
        </button>
      </div>
      <nav className="p-2 space-y-1">
        {items.map((it, i) => {
          const IconComponent = it.icon;
          return (
            <button
              key={i}
              className={
                "w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm " +
                (active === it.route ? "bg-muted font-medium" : "hover:bg-muted")
              }
              onClick={() => { if (onNavigate) onNavigate(it.route); window.scrollTo({ top: 0, behavior: "smooth" }); }}
            >
              <IconComponent className="w-5 h-5" />
              <span className={collapsed ? "sr-only" : "truncate"}>{it.label}</span>
            </button>
          );
        })}
      </nav>
    </aside>
  );
}
