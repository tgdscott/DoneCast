import React, { useState } from "react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { useToast } from "@/hooks/use-toast";
import { useAuth } from "@/AuthContext.jsx";
import { buildApiUrl } from "@/lib/apiClient.js";

export default function ClosedAlphaGate() {
  const { user, token, logout } = useAuth();
  const { toast } = useToast();
  const [email, setEmail] = useState(user?.email || "");
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const submit = async (e) => {
    e?.preventDefault?.();
    if (!email) return;
    setSubmitting(true);
    try {
      const r = await fetch(buildApiUrl('/api/public/waitlist'), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ email, note: note || undefined }),
      });
      if (r.ok) {
        toast({ title: "Request received", description: "We'll notify you as soon as a spot opens." });
        setNote("");
        // Redirect to main page after successful submission
        setTimeout(() => {
          window.location.href = '/';
        }, 2000);
      } else {
        let msg = "Please try again later.";
        try { const j = await r.json(); msg = j?.error?.message || j?.detail || msg; } catch {}
        toast({ title: "Couldn't save your request", description: msg, variant: "destructive" });
      }
    } catch (e2) {
      toast({ title: "Network error", description: "Check your connection and try again.", variant: "destructive" });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-50 to-white p-4">
      <Card className="w-full max-w-xl shadow-sm border-slate-200">
        <CardHeader>
          <CardTitle className="text-2xl">Private preview access</CardTitle>
        </CardHeader>
        <CardContent className="space-y-5 text-slate-700">
          <p>
            This application is currently in a closed alpha. If you've recently signed up and we recognize your email,
            your account will be approved shortly. If you'd like to join the pre-launch test group, leave your email below and
            we'll reach out as soon as new slots open.
          </p>

          <form onSubmit={submit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="note">Optional note</Label>
              <Input id="note" type="text" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Tell us a bit about your use case" />
            </div>
            <div className="flex items-center gap-3 pt-2">
              <Button type="submit" disabled={submitting}>{submitting ? "Sending..." : "Request early access"}</Button>
              <Button type="button" variant="outline" onClick={logout}>Sign out</Button>
            </div>
            <p className="text-xs text-slate-500">We'll only use your email to notify you about access and important updates. No spam.</p>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
