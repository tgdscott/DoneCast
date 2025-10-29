import React from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import CoverCropper from "@/components/dashboard/CoverCropper.jsx";

export default function CoverArtStep({ wizard }) {
  const {
    formData,
    handleChange,
    skipCoverNow,
    setSkipCoverNow,
    coverArtInputRef,
    coverCropperRef,
    coverCrop,
    setCoverCrop,
    setFormData,
    coverMode,
    setCoverMode,
  } = wizard;

  return (
    <div className="space-y-4">
      {!formData.coverArt && (
        <div className="space-y-2">
          <Label htmlFor="coverArt">Image</Label>
          <div>
            <Input
              ref={coverArtInputRef}
              id="coverArt"
              type="file"
              onChange={handleChange}
              accept="image/png, image/jpeg,image/jpg"
            />
            <p className="text-xs text-muted-foreground mt-2">
              You can resize and position your image below.
            </p>
          </div>
          <div className="flex items-center gap-2 mt-2">
            <input
              id="skipCoverNow"
              type="checkbox"
              checked={skipCoverNow}
              onChange={(event) => setSkipCoverNow(event.target.checked)}
            />
            <Label htmlFor="skipCoverNow">Skip this for now</Label>
          </div>
        </div>
      )}
      {formData.coverArt && (
        <div className="space-y-3">
          <div className="grid grid-cols-4 items-start gap-4">
            <Label className="text-right">Adjust</Label>
            <div className="col-span-3">
              <CoverCropper
                ref={coverCropperRef}
                sourceFile={formData.coverArt}
                existingUrl={null}
                value={coverCrop}
                onChange={(value) => setCoverCrop(value)}
                onModeChange={(mode) => setCoverMode(mode)}
              />
              <div className="flex gap-2 mt-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    setFormData((prev) => ({ ...prev, coverArt: null }));
                    setCoverCrop(null);
                  }}
                >
                  Remove
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
