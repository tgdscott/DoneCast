import { useState } from "react";
import { AlertTriangle, Trash2, XCircle } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/hooks/use-toast";
import { makeApi } from "@/lib/apiClient";

export function AccountDeletionDialog({ open, onOpenChange, token, userEmail, onSuccess }) {
  const { toast } = useToast();
  const [confirmEmail, setConfirmEmail] = useState("");
  const [reason, setReason] = useState("");
  const [isDeleting, setIsDeleting] = useState(false);

  const handleDelete = async () => {
    if (confirmEmail.toLowerCase().trim() !== userEmail.toLowerCase().trim()) {
      toast({
        title: "Email doesn't match",
        description: "Please enter your email address exactly as shown.",
        variant: "destructive",
      });
      return;
    }

    setIsDeleting(true);
    try {
      const api = makeApi(token);
      const response = await api.post("/api/users/me/request-deletion", {
        confirm_email: confirmEmail.trim(),
        reason: reason.trim() || undefined,
      });

      toast({
        title: "Account deletion scheduled",
        description: response.message || "Your account will be deleted after the grace period.",
        variant: "default",
      });

      // Close dialog and trigger success callback
      onOpenChange(false);
      if (onSuccess) onSuccess(response);
    } catch (err) {
      toast({
        title: "Failed to schedule deletion",
        description: err?.message || "Please try again or contact support.",
        variant: "destructive",
      });
    } finally {
      setIsDeleting(false);
    }
  };

  const handleCancel = () => {
    setConfirmEmail("");
    setReason("");
    onOpenChange(false);
  };

  const isEmailValid = confirmEmail.toLowerCase().trim() === userEmail.toLowerCase().trim();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[600px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-red-600">
            <AlertTriangle className="h-5 w-5" />
            Delete Your Account
          </DialogTitle>
          <DialogDescription className="space-y-3 pt-2">
            <p className="font-semibold text-foreground">
              This action cannot be undone immediately. Here's what will happen:
            </p>
            <ul className="list-disc list-inside space-y-1 text-sm">
              <li>Your account will enter a grace period (2-30 days based on your content)</li>
              <li>During the grace period, you can cancel and restore your account</li>
              <li>After the grace period, all your data will be permanently deleted</li>
              <li>All podcasts, episodes, media files, and settings will be removed</li>
              <li>Published RSS feeds will stop working</li>
              <li>This cannot be reversed after the grace period ends</li>
            </ul>
            <p className="text-sm font-medium text-amber-600 bg-amber-50 p-3 rounded-md border border-amber-200">
              ⚠️ Grace period length depends on published episodes (2 days minimum + 7 days per published episode)
            </p>
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="confirm-email" className="text-sm font-semibold">
              Confirm your email address
            </Label>
            <p className="text-xs text-muted-foreground mb-2">
              Type <span className="font-mono font-semibold text-foreground">{userEmail}</span> to confirm
            </p>
            <Input
              id="confirm-email"
              type="email"
              placeholder={userEmail}
              value={confirmEmail}
              onChange={(e) => setConfirmEmail(e.target.value)}
              className={confirmEmail && !isEmailValid ? "border-red-300 focus-visible:ring-red-400" : ""}
            />
            {confirmEmail && !isEmailValid && (
              <p className="text-xs text-red-600 flex items-center gap-1">
                <XCircle className="h-3 w-3" />
                Email doesn't match
              </p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="deletion-reason" className="text-sm font-semibold">
              Reason for leaving (optional)
            </Label>
            <Textarea
              id="deletion-reason"
              placeholder="Help us improve by sharing why you're leaving..."
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={3}
              className="resize-none"
            />
            <p className="text-xs text-muted-foreground">
              Your feedback helps us make Podcast Plus Plus better for everyone.
            </p>
          </div>
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button
            type="button"
            variant="outline"
            onClick={handleCancel}
            disabled={isDeleting}
          >
            Cancel
          </Button>
          <Button
            type="button"
            variant="destructive"
            onClick={handleDelete}
            disabled={!isEmailValid || isDeleting}
            className="gap-2"
          >
            <Trash2 className="h-4 w-4" />
            {isDeleting ? "Scheduling deletion..." : "Schedule Account Deletion"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function CancelDeletionDialog({ open, onOpenChange, token, onSuccess }) {
  const { toast } = useToast();
  const [isCancelling, setIsCancelling] = useState(false);

  const handleCancel = async () => {
    setIsCancelling(true);
    try {
      const api = makeApi(token);
      const response = await api.post("/api/users/me/cancel-deletion");

      toast({
        title: "Account deletion cancelled",
        description: response.message || "Your account has been restored.",
        variant: "default",
      });

      onOpenChange(false);
      if (onSuccess) onSuccess(response);
    } catch (err) {
      toast({
        title: "Failed to cancel deletion",
        description: err?.message || "Please try again or contact support.",
        variant: "destructive",
      });
    } finally {
      setIsCancelling(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-green-600">
            <XCircle className="h-5 w-5" />
            Cancel Account Deletion
          </DialogTitle>
          <DialogDescription className="space-y-3 pt-2">
            <p className="text-foreground">
              Your account is currently scheduled for deletion. You can cancel this and restore your account immediately.
            </p>
            <p className="text-sm">
              All your data is still intact and will remain accessible after cancellation.
            </p>
          </DialogDescription>
        </DialogHeader>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isCancelling}
          >
            Close
          </Button>
          <Button
            type="button"
            variant="default"
            onClick={handleCancel}
            disabled={isCancelling}
            className="gap-2 bg-green-600 hover:bg-green-700"
          >
            {isCancelling ? "Cancelling..." : "Restore My Account"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
