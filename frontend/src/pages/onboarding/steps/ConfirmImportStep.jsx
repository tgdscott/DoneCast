import React from "react";

export default function ConfirmImportStep({ wizard }) {
  const { rssUrl } = wizard;

  return (
    <div className="space-y-3">
      <p className="text-sm">We'll import episodes and assets from:</p>
      <div className="p-3 rounded border bg-accent/30 text-sm break-all">{rssUrl || '-'}</div>
      <p className="text-xs text-muted-foreground">Click Continue to start the import.</p>
    </div>
  );
}
