"use client";

import React from "react";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { useLayout } from "@/layout/LayoutContext.jsx";
import { LAYOUT_MODE_KEY, LAYOUT_STORAGE_KEY } from "@/layout/LayoutContext.jsx";

function ensureAssignment() {
  try {
    const saved = localStorage.getItem(LAYOUT_STORAGE_KEY);
    if (saved === "regular" || saved === "ab") return saved;
    const assigned = Math.random() < 0.5 ? "regular" : "ab";
    localStorage.setItem(LAYOUT_STORAGE_KEY, assigned);
    return assigned;
  } catch {
    return "regular";
  }
}

export default function AdminLayoutToggle() {
  const { layoutKey, layoutMode } = useLayout();
  const [value, setValue] = React.useState(layoutMode === "auto" ? "auto" : layoutKey);

  React.useEffect(() => {
    setValue(layoutMode === "auto" ? "auto" : layoutKey);
  }, [layoutKey, layoutMode]);

  const apply = (next) => {
    try {
      if (next === "auto") {
        ensureAssignment();
        localStorage.setItem(LAYOUT_MODE_KEY, "auto");
      } else {
        localStorage.setItem(LAYOUT_STORAGE_KEY, next);
        localStorage.setItem(LAYOUT_MODE_KEY, "manual");
      }
    } catch {}
    window.location.reload();
  };

  const currentLabel = layoutKey === "ab" ? "Plus Plus workspace" : "Regular workspace";
  const modeLabel = layoutMode === "auto" ? "Auto (50/50)" : "Manual";

  return (
    <div className="flex items-center justify-between">
      <div>
        <Label className="text-base font-medium text-gray-700">Workspace layout experiment</Label>
        <p className="text-sm text-gray-500 mt-1">
          Choose between the classic dashboard and the newer Plus Plus workspace, or let visitors split 50/50.
        </p>
        <p className="text-xs text-muted-foreground mt-2">
          Current mode: {modeLabel}. Active bucket: {currentLabel}.
        </p>
      </div>

      <div className="flex items-center gap-2">
        <Select value={value} onValueChange={setValue}>
          <SelectTrigger className="w-[220px]">
            <SelectValue placeholder="Select layout…" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="regular">Regular workspace</SelectItem>
            <SelectItem value="ab">Plus Plus workspace</SelectItem>
            <SelectItem value="auto">Auto 50/50</SelectItem>
          </SelectContent>
        </Select>
        <Button variant="default" onClick={() => apply(value)}>Apply</Button>
      </div>
    </div>
  );
}
