import { useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { AlertTriangle, Loader2 } from "lucide-react";

export default function ResetConfirmDialog({ 
  isOpen, 
  onClose, 
  onConfirm,
  isLoading 
}) {
  const [confirmText, setConfirmText] = useState("");
  const isValid = confirmText.trim().toLowerCase() === "here comes the boom";

  const handleConfirm = () => {
    if (isValid) {
      onConfirm();
    }
  };

  const handleClose = () => {
    setConfirmText("");
    onClose();
  };

  return (
    <Dialog open={isOpen} onOpenChange={handleClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-red-600">
            <AlertTriangle className="h-5 w-5" />
            Reset Website to Defaults
          </DialogTitle>
          <DialogDescription>
            This will permanently delete all your customizations and reset the website to its initial state.
          </DialogDescription>
        </DialogHeader>

        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>
            <strong>Warning:</strong> This action cannot be undone. All sections, CSS, and customizations will be lost.
          </AlertDescription>
        </Alert>

        <div className="space-y-4">
          <div className="space-y-2">
            <label className="text-sm font-medium">
              Type <code className="bg-slate-100 px-1 py-0.5 rounded">here comes the boom</code> to confirm
            </label>
            <Input
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              placeholder="here comes the boom"
              disabled={isLoading}
              className={isValid ? "border-red-500" : ""}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={handleClose} disabled={isLoading}>
            Cancel
          </Button>
          <Button 
            variant="destructive" 
            onClick={handleConfirm} 
            disabled={!isValid || isLoading}
          >
            {isLoading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Resetting...
              </>
            ) : (
              "Reset Website"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
