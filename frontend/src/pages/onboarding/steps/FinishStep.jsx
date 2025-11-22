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
          <p className="text-sm text-muted-foreground mb-2">
            All set! We've created your podcast <strong>"{formData.podcastName || 'your show'}"</strong> and a default template.
          </p>
          <p className="text-sm text-muted-foreground">
            Click Finish to go to your dashboard where you can create your first episode.
          </p>
          {saving && <div className="text-xs text-muted-foreground mt-2">Working...</div>}
        </>
      )}
    </div>
  );
}
