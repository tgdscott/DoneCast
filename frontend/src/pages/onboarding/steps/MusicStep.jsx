import React from "react";
import { Play, Pause } from "lucide-react";

export default function MusicStep({ wizard }) {
  const {
    musicAssets,
    musicLoading,
    musicChoice,
    setMusicChoice,
    musicPreviewing,
    toggleMusicPreview,
  } = wizard;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        {musicLoading ? "Loading music..." : 'Pick a track or choose "No Music".'}
      </div>
      <div className="grid gap-2">
        {musicAssets.map((asset) => {
          const canPreview = !!(
            asset && asset.id !== "none" && (asset.preview_url || asset.url || asset.filename)
          );
          const isActive = musicChoice === asset.id;
          const isPreviewing = musicPreviewing === asset.id;
          return (
            <div
              key={asset.id}
              className={`flex items-center gap-3 p-2 rounded border ${
                isActive ? "border-blue-600 bg-blue-50" : "bg-card hover:border-muted-foreground/30"
              }`}
            >
              <button
                type="button"
                aria-label={isPreviewing ? "Pause preview" : "Play preview"}
                disabled={!canPreview}
                onClick={() => canPreview && toggleMusicPreview(asset)}
                className={`inline-flex items-center justify-center h-8 w-8 rounded border ${
                  isPreviewing
                    ? "bg-blue-600 text-white border-blue-600"
                    : "bg-white text-foreground border-muted-foreground/30"
                } disabled:opacity-50`}
                title={canPreview ? "Preview 20s" : "Preview not available"}
              >
                {isPreviewing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
              </button>
              <label className="flex items-center gap-3 flex-1 cursor-pointer">
                <input
                  type="radio"
                  name="music"
                  value={asset.id}
                  checked={isActive}
                  onChange={() => setMusicChoice(asset.id)}
                />
                <div className="flex-1">
                  <div className="text-sm font-medium">{asset.display_name}</div>
                  {asset.mood_tags && asset.mood_tags.length > 0 && (
                    <div className="text-xs text-muted-foreground">
                      {asset.mood_tags.slice(0, 3).join(", ")}
                    </div>
                  )}
                </div>
              </label>
            </div>
          );
        })}
      </div>
    </div>
  );
}
