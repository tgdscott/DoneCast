"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/AuthContext.jsx";
import { useToast } from "@/hooks/use-toast";
import { makeApi } from '@/lib/apiClient';
import AdminFeatureToggles from "@/components/admin/AdminFeatureToggles.jsx";

export default function AdminSettings() {
  const { user, token } = useAuth();
  const { toast } = useToast();
  const [settings, setSettings] = useState(null);
  const [isAdmin, setIsAdmin] = useState(false);

  useEffect(() => {
    let canceled = false;
    (async () => {
      try {
        if (!token) {
          if (!canceled) {
            setIsAdmin(false);
            setSettings(null);
          }
          return;
        }
        // Only attempt admin fetch if user is known admin; otherwise skip noisy 403s
        if (!(user && (user.is_admin || user.role === 'admin'))) {
          if (!canceled) {
            setIsAdmin(false);
            setSettings(null);
          }
          return;
        }
        const data = await makeApi(token).get('/api/admin/settings');
        if (!canceled) {
          if (data) {
            setIsAdmin(true);
            setSettings(data);
          } else {
            setIsAdmin(false);
            setSettings(null);
          }
        }
      } catch (e) {
        if (!canceled) {
          setIsAdmin(false);
          setSettings(null);
          try { toast({ title: 'Error', description: 'Unable to load admin settings', variant: 'destructive' }); } catch {}
        }
      }
    })();
    return () => { canceled = true; };
  }, [token, user, toast]);

  if (!isAdmin) return null;

  return (
    <Card className="mt-4">
      <CardHeader>
        <CardTitle>Admin Settings</CardTitle>
      </CardHeader>
      <CardContent>
        <AdminFeatureToggles
          token={token}
          initial={settings}
          onSaved={setSettings}
        />
      </CardContent>
    </Card>
  );
}
