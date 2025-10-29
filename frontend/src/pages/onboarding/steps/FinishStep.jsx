import React from "react";

export default function FinishStep({ wizard }) {
  const { path, formData, saving } = wizard;
  const nameOk = (formData.podcastName || "").trim().length >= 4;
  const descOk = (formData.podcastDescription || "").trim().length > 0;
  const missingData = path === "new" && (!nameOk || !descOk);

  return (
    <div className="space-y-2">
      <h3 className="text-lg font-semibold">Finish</h3>
      {missingData ? (
        <div className="space-y-2">
          <p className="text-sm text-destructive">We're missing some required information:</p>
          <ul className="text-sm text-muted-foreground list-disc list-inside">
            {!nameOk && <li>Podcast name (at least 4 characters)</li>}
            {!descOk && <li>Podcast description</li>}
          </ul>
          <p className="text-sm text-muted-foreground">Please go back and fill in these details.</p>
        </div>
      ) : (
        <>
          <p className="text-sm text-muted-foreground">
            Nice work. You can publish now or explore your dashboard.
          </p>
          {saving && <div className="text-xs text-muted-foreground">Working...</div>}
        </>
      )}
    </div>
  );
}
