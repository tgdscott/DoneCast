import { useState, useEffect } from "react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Sparkles } from "lucide-react";

export default function ArtisticDirectionDialog({ 
  isOpen, 
  onClose, 
  onGenerate,
  isGenerating = false
}) {
  const [artisticDirection, setArtisticDirection] = useState("");

  useEffect(() => {
    if (isOpen) {
      setArtisticDirection("");
    }
  }, [isOpen]);

  const handleGenerate = () => {
    onGenerate(artisticDirection.trim() || null);
  };

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-purple-500" />
            Add Artistic Direction
          </DialogTitle>
          <DialogDescription>
            Want to customize your cover art? Add any specific directions for colors, fonts, style, mood, or design elements. 
            This will be combined with your podcast name and description.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <label htmlFor="artistic-direction" className="text-sm font-medium">
              Artistic Direction (Optional)
            </label>
            <Textarea
              id="artistic-direction"
              value={artisticDirection}
              onChange={(e) => setArtisticDirection(e.target.value)}
              placeholder="E.g., Use a dark theme with neon green accents, bold sans-serif font, minimalist design, tech/cyberpunk aesthetic..."
              rows={6}
              className="resize-none"
              disabled={isGenerating}
            />
            <p className="text-xs text-muted-foreground">
              Examples: "Use warm earth tones", "Bold, modern typography", "Vintage retro style", "Minimalist with geometric shapes"
            </p>
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={onClose}
            disabled={isGenerating}
          >
            Cancel
          </Button>
          <Button
            onClick={handleGenerate}
            disabled={isGenerating}
            className="bg-purple-600 hover:bg-purple-700"
          >
            {isGenerating ? (
              <>
                <Sparkles className="mr-2 h-4 w-4 animate-pulse" />
                Generating...
              </>
            ) : (
              <>
                <Sparkles className="mr-2 h-4 w-4" />
                Generate Cover Art
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}


