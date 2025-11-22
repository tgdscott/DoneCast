import React from "react";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { cn } from "@/lib/utils";

export default function DesignStep({ wizard }) {
  const {
    designVibe,
    setDesignVibe,
    colorPreference,
    setColorPreference,
    additionalNotes,
    setAdditionalNotes,
  } = wizard;

  const vibes = [
    "Clean & Minimal",
    "Bold & Energetic",
    "Professional & Corporate",
    "Warm & Friendly",
    "Dark & Cinematic",
    "Retro & Vintage",
  ];

  return (
    <div className="space-y-6 max-w-2xl animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="space-y-2">
        <h2 className="text-xl font-semibold">Website Style</h2>
        <p className="text-sm text-muted-foreground">
          We'll build a website for your podcast. Help us get the look right.
        </p>
      </div>

      <div className="space-y-3">
        <Label className="text-base">Visual Vibe</Label>
        <div className="grid grid-cols-2 gap-3">
          {vibes.map((vibe) => (
            <div
              key={vibe}
              onClick={() => setDesignVibe(vibe)}
              className={cn(
                "cursor-pointer rounded-lg border p-4 text-sm font-medium transition-all hover:bg-accent",
                designVibe === vibe
                  ? "border-primary bg-primary/5 ring-1 ring-primary"
                  : "border-input"
              )}
            >
              {vibe}
            </div>
          ))}
        </div>
      </div>

      <div className="space-y-3">
        <Label className="text-base">Color Preferences (Optional)</Label>
        <Input
          value={colorPreference}
          onChange={(e) => setColorPreference(e.target.value)}
          placeholder="e.g. Navy blue and gold, Pastels, Black and white, Neon green"
          className="max-w-md"
        />
        <p className="text-xs text-muted-foreground">
          If left blank, we'll extract colors from your cover art.
        </p>
      </div>

      <div className="space-y-3">
        <Label className="text-base">Additional Notes (Optional)</Label>
        <Textarea
          value={additionalNotes}
          onChange={(e) => setAdditionalNotes(e.target.value)}
          placeholder="Anything else about the look and feel? e.g. 'Make it look like a 1980s newspaper' or 'Use high contrast mode'"
          className="min-h-[100px]"
        />
      </div>
    </div>
  );
}

