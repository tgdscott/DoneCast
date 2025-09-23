"use client"

import { Button } from "@/components/ui/button";
import { ArrowLeft } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import AudioCleanupSettings from "@/components/dashboard/AudioCleanupSettings";
import AdminSettings from "@/components/dashboard/AdminSettings";
import ComfortMenu from "@/components/common/ComfortMenu.jsx";
import { useToast } from "@/hooks/use-toast";
import { useEffect, useState, useRef, useCallback } from "react";
import { useAuth } from "@/AuthContext.jsx";
import { makeApi, buildApiUrl } from "@/lib/apiClient";

export default function Settings({ token }) {
  const { toast } = useToast();
  const { user: authUser, refreshUser } = useAuth();
  const [isSpreakerConnected, setIsSpreakerConnected] = useState(false);
  const pollRef = useRef(null);

  const announceConnected = useCallback(() => {
    setIsSpreakerConnected(prev => {
      if (!prev) {
        toast({ title: 'Spreaker Connected', description: 'Your Spreaker account has been successfully connected!' });
      }
      return true;
    });
  }, [toast]);

  const verifyConnection = useCallback(async () => {
    if (!token) return false;
    try {
      const user = await makeApi(token).get('/api/auth/users/me');
      if (user?.spreaker_access_token) {
        announceConnected();
        refreshUser?.({ force: true });
        return true;
      }
    } catch (_) {}
    return false;
  }, [announceConnected, refreshUser, token]);

  useEffect(() => {
    setIsSpreakerConnected(!!authUser?.spreaker_access_token);
  }, [authUser]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get('spreaker_connected') === 'true') {
      announceConnected();
      verifyConnection().catch(() => {});
      window.history.replaceState({}, document.title, window.location.pathname);
    }
  }, [announceConnected, verifyConnection]);

  useEffect(() => {
    const handleMessage = (event) => {
      // Accept messages from our app origin and API origin (popup runs on API domain)
      let allowed = new Set([window.location.origin]);
      try {
        const apiBase = buildApiUrl("");
        if (apiBase) {
          const apiOrigin = new URL(apiBase).origin;
          allowed.add(apiOrigin);
        }
      } catch (_) {}
      if (!allowed.has(event.origin)) return;
      const data = event.data;
      if (data === 'spreaker_connected' || (data && data.type === 'spreaker_connected')) {
        if (pollRef.current) {
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
        announceConnected();
        verifyConnection().catch(() => {});
      }
    };

    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [announceConnected, verifyConnection]);

  useEffect(() => {
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, []);

  const handleConnectSpreaker = async () => {
    try {
      // Safer default: legacy flow that returns { auth_url } matches deployed redirect_uri most likely
      let popupUrl = null;
      try {
        const { auth_url } = await makeApi(token).get('/api/spreaker/auth/login');
        popupUrl = auth_url;
      } catch (_) {
        // Fallback to new popup flow via /api/auth/spreaker/start with JWT in query (no headers in popup)
        if (token) {
          const qs = new URLSearchParams({ access_token: token }).toString();
          popupUrl = buildApiUrl(`/api/auth/spreaker/start?${qs}`);
        }
      }
      if (!popupUrl) throw new Error('Could not start the Spreaker sign-in.');
      const popup = window.open(popupUrl, 'spreakerAuth', 'width=600,height=700');
      if (!popup) throw new Error('Popup blocked. Please allow popups and try again.');
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
      pollRef.current = setInterval(async () => {
        if (!popup || popup.closed) {
          if (pollRef.current) {
            clearInterval(pollRef.current);
            pollRef.current = null;
          }
          await verifyConnection();
        }
      }, 1000);
    } catch (err) {
      toast({ title: 'Connection Error', description: err?.message || 'An unexpected error occurred.', variant: 'destructive' });
    }
  };

  const handleDisconnectSpreaker = async () => {
    if (!window.confirm("Are you sure you want to disconnect your Spreaker account?")) return;
    try {
  const api = makeApi(token);
  await api.post('/api/spreaker/disconnect', {});
        toast({ title: "Spreaker Disconnected", description: "Your Spreaker account has been successfully disconnected." });
  refreshUser({ force:true });
    } catch (err) {
  toast({ title: "Error", description: err.message || "An unexpected error occurred.", variant: "destructive" });
    }
  };

  const goBack = () => {
    // Redirect to root; App will route to correct dashboard
    window.location.href = '/';
  };

  return (
    <div className="p-6 bg-white rounded-xl shadow-md space-y-4">
      <div>
        <button
          onClick={goBack}
          className="flex items-center text-sm text-gray-600 hover:text-gray-900 group"
          aria-label="Back to dashboard"
        >
          <ArrowLeft className="w-4 h-4 mr-1 transition-transform group-hover:-translate-x-0.5" />
          <span>Back to Dashboard</span>
        </button>
      </div>
  <Card>
        <CardHeader>
          <CardTitle>Your Settings</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <div>
              <h3 className="text-lg font-medium">Display preferences</h3>
              <p className="text-sm text-muted-foreground mb-2">Adjust text size and contrast to make the workspace easier to use.</p>
              <ComfortMenu inline className="mt-3" />
            </div>
            <div>
              <h3 className="text-lg font-medium">Your profile</h3>
              <p className="text-sm text-muted-foreground mb-2">We’ll use this to say hello and label your work.</p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-2">
                <div>
                  <label className="block text-xs font-semibold mb-1 uppercase tracking-wide">First name</label>
                  <input type="text" defaultValue={authUser?.first_name || ''} id="firstNameInput" className="w-full border rounded px-2 py-2 text-sm" placeholder="Jane" />
                </div>
                <div>
                  <label className="block text-xs font-semibold mb-1 uppercase tracking-wide">Last name</label>
                  <input type="text" defaultValue={authUser?.last_name || ''} id="lastNameInput" className="w-full border rounded px-2 py-2 text-sm" placeholder="Doe" />
                </div>
              </div>
              <Button variant="secondary" onClick={async ()=>{
                const first = document.getElementById('firstNameInput').value;
                const last = document.getElementById('lastNameInput').value;
                try {
                  const api = makeApi(token);
                  await api.patch('/api/auth/users/me/prefs', { first_name:first, last_name:last });
                  toast({ title:'Saved your profile'});
                  refreshUser({ force:true });
                } catch (e) {
                  toast({ title:'Error', description: e.message || 'Could not update profile', variant:'destructive'});
                }
              }}>Save Profile</Button>
            </div>
            <div>
              <h3 className="text-lg font-medium">Publish to Spreaker</h3>
              <p className="text-sm text-muted-foreground">Connect your Spreaker account so finished episodes can be posted for you.</p>
            </div>
            <div className="flex items-center justify-between p-4 border rounded-md">
              <div>
                <h4 className="font-semibold">Spreaker</h4>
                <p className="text-sm text-muted-foreground">One-time connect, then you can send shows with one click.</p>
              </div>
              {isSpreakerConnected ? (
                <div className="flex items-center space-x-2">
                  <span className="text-green-600 font-medium">Connected</span>
                  <Button onClick={handleDisconnectSpreaker} variant="destructive">Disconnect</Button>
                </div>
              ) : (
                <Button onClick={handleConnectSpreaker}>Connect to Spreaker</Button>
              )}
            </div>
      </div>
        </CardContent>
      </Card>
  <AudioCleanupSettings />
  <AdminSettings />
      {/* Small A/B Workspace link at the very bottom */}
      <div className="pt-6">
        <button
          type="button"
          onClick={() => { try { window.location.href = '/ab'; } catch(_) {} }}
          className="text-xs text-muted-foreground hover:underline font-normal"
        >
          A/B workspace
        </button>
      </div>
    </div>
  );
}