import { useState } from "react";
import termsHtml from "@/legal/terms-of-use.html?raw";
import { useAuth } from "@/AuthContext.jsx";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardContent, CardFooter } from "@/components/ui/card";

export default function TermsGate() {
  const { user, acceptTerms, logout } = useAuth();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
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
            <Button variant="outline" onClick={logout} disabled={submitting}>
              Sign out
            </Button>
            <Button onClick={handleAccept} disabled={submitting}>
              {submitting ? 'Recording acceptance…' : 'I Agree'}
            </Button>
          </CardFooter>
        </Card>
      </div>
    </div>
  );
}
