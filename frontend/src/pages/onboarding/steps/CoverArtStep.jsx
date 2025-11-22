import React, { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import CoverCropper from "@/components/dashboard/CoverCropper.jsx";
import { Sparkles } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import ArtisticDirectionDialog from "@/components/onboarding/ArtisticDirectionDialog.jsx";

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
    token,
    generateCoverArt,
  } = wizard;
  const [isGenerating, setIsGenerating] = useState(false);
  const [showArtisticDirectionDialog, setShowArtisticDirectionDialog] = useState(false);
  const { toast } = useToast();

  const handleGenerateClick = () => {
    if (!formData.podcastName || formData.podcastName.trim().length < 4) {
      toast({
        variant: "destructive",
        title: "Podcast name required",
        description: "Please enter your podcast name in the 'About your show' step first.",
      });
      return;
    }
    setShowArtisticDirectionDialog(true);
  };

  const handleGenerateCover = async (artisticDirection = null) => {
    setShowArtisticDirectionDialog(false);
    setIsGenerating(true);
    try {
      const file = await generateCoverArt(artisticDirection);
      if (file) {
        setFormData((prev) => ({ ...prev, coverArt: file }));
        setCoverCrop(null);
        toast({
          title: "Cover art generated!",
          description: "You can adjust it below or generate a new one.",
        });
      }
    } catch (error) {
      toast({
        variant: "destructive",
        title: "Generation failed",
        description: error.message || "Failed to generate cover art. Please try again.",
      });
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <div className="space-y-4">
      {!formData.coverArt && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label htmlFor="coverArt">Image</Label>
            <div className="flex items-center gap-2">
              <input
                id="skipCoverNow"
                type="checkbox"
                checked={skipCoverNow}
                onChange={(event) => setSkipCoverNow(event.target.checked)}
              />
              <Label htmlFor="skipCoverNow" className="text-sm font-normal cursor-pointer">
                Skip this for now
              </Label>
            </div>
          </div>
          <div className="space-y-3">
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
            <div className="flex items-center gap-2">
              <div className="h-px bg-border flex-1" />
              <span className="text-xs text-muted-foreground">or</span>
              <div className="h-px bg-border flex-1" />
            </div>
            <Button
              type="button"
              variant="outline"
              onClick={handleGenerateClick}
              disabled={isGenerating || !formData.podcastName || formData.podcastName.trim().length < 4}
              className="w-full"
            >
              <Sparkles className="mr-2 h-4 w-4" />
              {isGenerating ? "Generating..." : "Generate with AI"}
            </Button>
            <ArtisticDirectionDialog
              isOpen={showArtisticDirectionDialog}
              onClose={() => setShowArtisticDirectionDialog(false)}
              onGenerate={handleGenerateCover}
              isGenerating={isGenerating}
            />
            {(!formData.podcastName || formData.podcastName.trim().length < 4) && (
              <p className="text-xs text-muted-foreground text-center">
                Enter your podcast name first to generate cover art
              </p>
            )}
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
