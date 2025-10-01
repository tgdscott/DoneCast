import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

const GenerateVoiceDialog = ({
  open,
  onOpenChange,
  script,
  onScriptChange,
  voiceId,
  onVoiceChange,
  voices,
  friendlyName,
  onFriendlyNameChange,
  onSubmit,
  onCancel,
  isLoading,
  canSubmit,
}) => (
  <Dialog open={open} onOpenChange={onOpenChange}>
    <DialogContent className="sm:max-w-[600px]">
      <DialogHeader>
        <DialogTitle>Generate with AI voice (one-time)</DialogTitle>
        <DialogDescription>
          We'll synthesize this once and save it to your library. You won't need to regenerate it every episode.
        </DialogDescription>
      </DialogHeader>
      <div className="space-y-4 py-2">
        <div>
          <Label>Script</Label>
          <Textarea
            value={script}
            onChange={(event) => onScriptChange(event.target.value)}
            placeholder="e.g., Welcome to the show..."
            className="mt-1"
            rows={5}
          />
        </div>
        <div>
          <Label>Voice</Label>
          <Select value={voiceId || ""} onValueChange={onVoiceChange}>
            <SelectTrigger className="mt-1">
              <SelectValue placeholder="Select a voice" />
            </SelectTrigger>
            <SelectContent>
              {voices.map((voice) => (
                <SelectItem key={voice.voice_id || voice.id || voice.name} value={voice.voice_id || voice.id || ""}>
                  {voice.common_name || voice.name || voice.voice_id || voice.id}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label>Friendly name (optional)</Label>
          <Input value={friendlyName} onChange={(event) => onFriendlyNameChange(event.target.value)} placeholder="e.g., Victoria's Intro" />
        </div>
      </div>
      <DialogFooter>
        <Button variant="outline" onClick={onCancel}>
          Cancel
        </Button>
        <Button disabled={!canSubmit || isLoading} onClick={onSubmit}>
          {isLoading ? "Creating clip..." : "Create clip"}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
);

export default GenerateVoiceDialog;
