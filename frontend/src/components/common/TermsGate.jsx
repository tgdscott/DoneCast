import { useState } from "react";
import termsHtml from "@/legal/terms-of-use.html?raw";
import { useAuth } from "@/AuthContext.jsx";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardContent, CardFooter } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";

export default function TermsGate() {
  const { user, acceptTerms, submitTermsConcern, logout } = useAuth();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [showConcernDialog, setShowConcernDialog] = useState(false);
  const [concern, setConcern] = useState('');
  const [submittingConcern, setSubmittingConcern] = useState(false);
  const [concernSubmitted, setConcernSubmitted] = useState(false);
  const versionRequired = user?.terms_version_required || user?.terms_version_accepted || '';

  const handleAccept = async () => {
    if (!versionRequired) return;
    setSubmitting(true);
    setError('');
    try {
      await acceptTerms(versionRequired);
    } catch (err) {
      const detail = err?.detail || err?.message || 'Unable to record acceptance. Please try again.';
      setError(detail);
    } finally {
      setSubmitting(false);
    }
  };

  const handleNotAgree = () => {
    setShowConcernDialog(true);
  };

  const handleSubmitConcern = async () => {
    if (!concern.trim()) {
      setError('Please describe your concern about the Terms of Service.');
      return;
    }
    setSubmittingConcern(true);
    setError('');
    try {
      const result = await submitTermsConcern(concern.trim());
      setConcernSubmitted(true);
      // Close dialog after a moment to show the success message
      setTimeout(() => {
        setShowConcernDialog(false);
        setConcern('');
        setConcernSubmitted(false);
        // User will need to sign out since they didn't agree to terms
      }, 3000);
    } catch (err) {
      const detail = err?.detail || err?.message || 'Unable to submit concern. Please try again.';
      setError(detail);
    } finally {
      setSubmittingConcern(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-100 py-10">
      <div className="mx-auto w-full max-w-4xl px-4">
        <Card className="shadow-xl">
          <CardHeader>
            <CardTitle className="text-2xl font-semibold text-slate-900">
              Updated Terms of Use
            </CardTitle>
            <p className="text-sm text-slate-600">
              To continue using Podcast Plus Plus we need you to review and accept the most recent terms. The full agreement is below for your records.
            </p>
          </CardHeader>
          <CardContent>
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3 text-sm text-slate-600">
              <div>
                <span className="font-medium text-slate-800">Required version:</span>{' '}
                {versionRequired || 'Unspecified'}
              </div>
              <div>
                Need a larger view?{' '}
                <a href="/terms" target="_blank" rel="noreferrer" className="font-medium text-blue-600 hover:text-blue-700">
                  Open the Terms in a new tab
                </a>
              </div>
            </div>
            <div className="max-h-[60vh] overflow-y-auto rounded-lg border border-slate-200 bg-white p-6">
              <article className="prose prose-slate max-w-none" dangerouslySetInnerHTML={{ __html: termsHtml }} />
            </div>
            {error && (
              <div className="mt-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
                {error}
              </div>
            )}
          </CardContent>
          <CardFooter className="flex flex-col items-stretch gap-3 md:flex-row md:justify-end">
            <Button variant="outline" onClick={logout} disabled={submitting || submittingConcern}>
              Sign out
            </Button>
            <Button 
              variant="destructive" 
              onClick={handleNotAgree} 
              disabled={submitting || submittingConcern}
            >
              I do NOT agree
            </Button>
            <Button onClick={handleAccept} disabled={submitting || submittingConcern}>
              {submitting ? 'Recording acceptance…' : 'I Agree'}
            </Button>
          </CardFooter>
        </Card>
      </div>

      <Dialog open={showConcernDialog} onOpenChange={setShowConcernDialog}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle>Terms of Service Concern</DialogTitle>
            <DialogDescription>
              What is it about the Terms of Service that concerns you?
            </DialogDescription>
          </DialogHeader>
          {concernSubmitted ? (
            <div className="py-4">
              <p className="text-sm text-green-700">
                Thank you for your feedback. Someone will review your concern and get back to you soon to address it.
              </p>
            </div>
          ) : (
            <>
              <div className="grid gap-4 py-4">
                <div className="grid gap-2">
                  <Label htmlFor="concern">Your Concern</Label>
                  <Textarea
                    id="concern"
                    placeholder="Please describe what concerns you about the Terms of Service..."
                    value={concern}
                    onChange={(e) => setConcern(e.target.value)}
                    rows={6}
                    disabled={submittingConcern}
                  />
                </div>
                {error && (
                  <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
                    {error}
                  </div>
                )}
              </div>
              <DialogFooter>
                <Button
                  variant="outline"
                  onClick={() => {
                    setShowConcernDialog(false);
                    setConcern('');
                    setError('');
                  }}
                  disabled={submittingConcern}
                >
                  Cancel
                </Button>
                <Button onClick={handleSubmitConcern} disabled={submittingConcern || !concern.trim()}>
                  {submittingConcern ? 'Submitting…' : 'Submit'}
                </Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
