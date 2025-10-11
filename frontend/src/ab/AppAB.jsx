
import React, { useState, useMemo, useCallback, useEffect } from "react";
import TopBar from "./components/TopBar";
import SideBar from "./components/SideBar";
import Dashboard from "./pages/Dashboard";
import CreatorUpload from "./pages/CreatorUpload";
import CreatorFinalize from "./pages/CreatorFinalize";
import Settings from "./pages/Settings";
// In-context views from the main app to avoid leaving the Plus Plus workspace
import MediaLibrary from "@/components/dashboard/MediaLibrary.jsx";
import TemplateManager from "@/components/dashboard/TemplateManager.jsx";
import BillingPage from "@/components/dashboard/BillingPage.jsx";
import EpisodeHistory from "@/components/dashboard/EpisodeHistory.jsx";
import PodcastManager from "@/components/dashboard/PodcastManager.jsx";
import PodcastCreator from "@/components/dashboard/PodcastCreator.jsx";
import { abApi } from "./lib/abApi";
import Recorder from "@/components/quicktools/Recorder.jsx";
import { makeApi } from "@/lib/apiClient";
import AIAssistant from "@/components/assistant/AIAssistant";
import { useAuth } from "@/AuthContext";

export default function AppAB({ token }) {
  const { user } = useAuth();
  const [active, setActive] = useState("dashboard");
  const [collapsed, setCollapsed] = useState(false);

  const [shows, setShows] = useState([]);

  // Start with no demo uploads or drafts; real items will appear as the user uploads
  const [uploads, setUploads] = useState([]);
  const [drafts, setDrafts] = useState([]);
  const [templates, setTemplates] = useState([]);
  
  // When auth changes, reset in-memory workspace state to avoid cross-account mixing
  useEffect(() => {
    setUploads([]);
    setDrafts([]);
    setShows([]);
  }, [token]);

  // Rehydrate client-side workspace state from localStorage (for immediate UX, even before server fetch)
  useEffect(() => {
    try {
      const k = token ? `ab_state_${token.slice(0,6)}` : 'ab_state_demo';
      const raw = localStorage.getItem(k);
      if (raw) {
        const j = JSON.parse(raw);
        if (Array.isArray(j.uploads)) setUploads(j.uploads);
        if (Array.isArray(j.drafts)) setDrafts(j.drafts);
      }
    } catch {}
  }, [token]);

  // Persist minimal workspace state so uploads don’t disappear if server lags
  useEffect(() => {
    try {
      const k = token ? `ab_state_${token.slice(0,6)}` : 'ab_state_demo';
      const state = { uploads, drafts };
      localStorage.setItem(k, JSON.stringify(state));
    } catch {}
  }, [uploads, drafts, token]);

  useEffect(() => {
    let abort = false;
    (async () => {
      try {
        const data = await makeApi(token).get('/api/templates/');
        if (!abort) setTemplates(Array.isArray(data) ? data : []);
      } catch {}
    })();
    return () => { abort = true; };
  }, [token]);

  // Load real podcasts for Plus Plus dashboard when signed in
  useEffect(() => {
    let aborted = false;
    (async () => {
      if (!token) return;
      try {
        const list = await abApi(token).listPodcasts();
        if (aborted) return;
        // Normalize shape: ensure id and name fields exist
        const mapped = (Array.isArray(list) ? list : []).map(p => ({ id: p.id || p.uuid || p._id || String(p.name || 'show'), name: p.name || p.title || 'Show' }));
        setShows(mapped);
      } catch {}
    })();
    return () => { aborted = true; };
  }, [token]);

  // Rehydrate uploads (and seed lightweight drafts) from server so items persist across refresh/new windows
  useEffect(() => {
    let aborted = false;
    (async () => {
      if (!token) return; // unauth demo mode has no server persistence
      try {
        const items = await abApi(token).listMedia();
        if (aborted) return;
        // Only surface main content uploads here; intro/outro/sound effects belong to template/media tools
        const mapped = (items || [])
          .filter((it) => {
            const cat = (it?.category || '').toLowerCase();
            return cat === 'main_content' || cat === 'content' || cat === '' || cat === 'audio';
          })
          .map((it) => {
          const sizeLabel = it?.size ? `${Math.max(1, Math.round(it.size/1024/1024))} MB` : "";
          const clientName = it?.friendly_name || it?.client_name || it?.filename || "audio";
          return {
            id: it.id,
            fileName: clientName,
            serverFilename: it.filename,
            size: sizeLabel,
            status: 'done',
            progress: 100,
            nickname: '',
            showId: undefined,
            ttlDays: 14,
          };
        });

        // Merge into existing uploads without duplicating by id
        setUploads((prev) => {
          const byId = new Map(prev.map((u) => [u.id, u]));
          mapped.forEach((m) => {
            const existing = byId.get(m.id);
            if (!existing) {
              byId.set(m.id, m);
            } else {
              // Update known fields (e.g., progress/status/name may improve)
              byId.set(m.id, { ...existing, ...m });
            }
          });
          return Array.from(byId.values());
        });

        // Seed minimal drafts so transcript status pills render sensibly
        setDrafts((prev) => {
          const have = new Set(prev.map((d) => d.fileId));
          const extras = mapped
            .filter((m) => !have.has(m.id))
            .map((m) => ({
              id: `d_${m.id}`,
              title: (m.fileName || '').replace(/\.[a-z0-9]+$/i, ''),
              fileId: m.id,
              transcript: 'processing',
              hint: (m.serverFilename || m.fileName || '').replace(/\.[a-z0-9]+$/i, ''),
            }));
          return extras.length ? prev.concat(extras) : prev;
        });
      } catch {
        // ignore
      }
    })();
    return () => { aborted = true; };
  }, [token]);

  // Check transcript readiness for all "processing" drafts on mount/refresh
  // This prevents drafts from being stuck showing "processing" after a page reload/deployment
  // when the transcript is actually ready on the server
  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!token) return;
      
      // Find all drafts that show as "processing"
      const processingDrafts = drafts.filter(d => d.transcript === 'processing' && d.hint);
      if (processingDrafts.length === 0) return;

      // Check each one with the server
      for (const draft of processingDrafts) {
        if (cancelled) break;
        try {
          const res = await abApi(token).transcriptReady({ hint: draft.hint });
          if (cancelled) return;
          if (res && res.ready) {
            // Update this draft to show as ready
            setDrafts(prev => prev.map(d => 
              d.id === draft.id ? { ...d, transcript: 'ready' } : d
            ));
          }
        } catch {
          // Ignore errors, draft will stay as "processing" and normal polling will continue
        }
        // Small delay between checks to avoid hammering the API
        if (!cancelled && processingDrafts.indexOf(draft) < processingDrafts.length - 1) {
          await new Promise(resolve => setTimeout(resolve, 200));
        }
      }
    })();
    return () => { cancelled = true; };
  }, [token]); // Only run once on mount when token is available

  const uploadById = useMemo(() => Object.fromEntries(uploads.map(u => [u.id, u])), [uploads]);

  // Merge a freshly uploaded media item into the uploads list and seed a draft
  const handleSavedMedia = React.useCallback((item) => {
    if (!item) return;
    const m = {
      id: item.id,
      fileName: item.friendly_name || item.client_name || item.filename || 'audio',
      serverFilename: item.filename,
      size: item.size ? `${Math.max(1, Math.round(item.size/1024/1024))} MB` : '',
      status: 'done',
      progress: 100,
      nickname: '',
      showId: undefined,
      ttlDays: 14,
    };
    setUploads((prev) => {
      const byId = new Map(prev.map((u) => [u.id, u]));
      const ex = byId.get(m.id);
      byId.set(m.id, ex ? { ...ex, ...m } : m);
      return Array.from(byId.values());
    });
    setDrafts((prev) => {
      if (prev.some((d) => d.fileId === item.id)) return prev;
      const title = (m.fileName || '').replace(/\.[a-z0-9]+$/i, '');
      return prev.concat([{ id: `d_${item.id}`, title, fileId: item.id, transcript: 'processing', hint: (m.serverFilename || title).replace(/\.[a-z0-9]+$/i, '') }]);
    });
  }, []);

  // Listen for global saved events (from Recorder) as a safety net
  useEffect(() => {
    const onEvt = (e) => handleSavedMedia(e?.detail);
    window.addEventListener('ppp:media-uploaded', onEvt);
    return () => window.removeEventListener('ppp:media-uploaded', onEvt);
  }, [handleSavedMedia]);

  const openDraft = useCallback((draftId) => {
    const d = drafts.find(x => x.id === draftId);
    if (!d) return;
    setActive(d.transcript === "ready" ? "creator-finalize" : "creator-upload");
  }, [drafts]);

  const markUploadUsed = useCallback((fileId) => {
    setUploads(prev => prev.filter(u => u.id !== fileId));
  }, []);

  return (
    <div className="min-h-screen flex flex-col">
      <TopBar active={active} onSwitch={setActive} />
      <div className="flex-1 flex">
        <SideBar collapsed={collapsed} setCollapsed={setCollapsed} onNavigate={setActive} active={active} />
        <main className="flex-1">
          {/* Subtle breadcrumbs to keep context inside the Plus Plus workspace */}
          <div className="px-4 pt-3 text-xs text-muted-foreground">
            {(() => {
              const labels = {
                dashboard: 'Dashboard',
                'episode-history': 'Episodes',
                'podcast-manager': 'My Podcasts',
                'media-library': 'Media Uploads',
                'my-templates': 'My Templates',
                billing: 'Billing',
                'creator-upload': 'Upload',
                'creator-finalize': 'Finalize',
                settings: 'Settings',
              };
              const here = labels[active] || '—';
              return (<span>Plus Plus workspace / <span className="text-foreground">{here}</span></span>);
            })()}
          </div>
          
      {active === "dashboard" && (
            <Dashboard
        token={token}
              shows={shows}
              drafts={drafts}
              onOpenDraft={openDraft}
              setActive={setActive}
            />
          )}
          {active === "episode-history" && (
            <EpisodeHistory token={token} onBack={() => setActive("dashboard")} />
          )}
          {active === "podcast-manager" && (
            <PodcastManager token={token} podcasts={shows} setPodcasts={setShows} onBack={() => setActive("dashboard")} />
          )}
          {active === "media-library" && (
            <MediaLibrary token={token} onBack={() => setActive("dashboard")} />
          )}
          {active === "my-templates" && (
            <TemplateManager token={token} onBack={() => setActive("dashboard")} setCurrentView={() => {}} />
          )}
          {active === "billing" && (
            <BillingPage token={token} onBack={() => setActive("dashboard")} />
          )}
          {active === "creator-upload" && (
            <CreatorUpload
              token={token}
              shows={shows}
              uploads={uploads}
              setUploads={setUploads}
              drafts={drafts}
              setDrafts={setDrafts}
              markUploadUsed={markUploadUsed}
              goFinalize={() => setActive("creator-finalize")}
              goCustomizeSegments={() => setActive("creator-step3")}
            />
          )}
          {active === "creator-finalize" && (
            <CreatorFinalize
              token={token}
              drafts={drafts}
              uploads={uploads}
              uploadById={uploadById}
              goUpload={() => setActive("creator-upload")}
            />
          )}
          {active === "creator-step3" && (
            <PodcastCreator
              onBack={() => setActive("creator-upload")}
              token={token}
              templates={templates}
              podcasts={shows}
              initialStep={3}
            />
          )}
          {active === "recorder" && (
            <Recorder
              onBack={() => setActive("dashboard")}
              token={token}
              onSaved={handleSavedMedia}
              onFinish={({ filename, hint, transcriptReady }) => {
                // Refresh uploads from server and seed/advance a draft for this recording
                (async () => {
                  try {
                    const items = await abApi(token).listMedia();
                    const filtered = (items || []).filter((it) => {
                      const cat = (it?.category || '').toLowerCase();
                      return cat === 'main_content' || cat === 'content' || cat === '' || cat === 'audio';
                    });
                    // Merge uploads by id
                    setUploads((prev) => {
                      const byId = new Map(prev.map((u) => [u.id, u]));
                      filtered.forEach((it) => {
                        const sizeLabel = it?.size ? `${Math.max(1, Math.round(it.size/1024/1024))} MB` : "";
                        const clientName = it?.friendly_name || it?.client_name || it?.filename || "audio";
                        const m = {
                          id: it.id,
                          fileName: clientName,
                          serverFilename: it.filename,
                          size: sizeLabel,
                          status: 'done',
                          progress: 100,
                          nickname: '',
                          showId: undefined,
                          ttlDays: 14,
                        };
                        const ex = byId.get(m.id);
                        byId.set(m.id, ex ? { ...ex, ...m } : m);
                      });
                      return Array.from(byId.values());
                    });

                    // Try to identify the recorded file by hint or exact filename
                    const match = filtered.find((it) => {
                      const fn = (it?.filename || '').toLowerCase();
                      const h = (hint || filename || '').toLowerCase();
                      if (!h) return false;
                      return fn === h || fn.includes(h);
                    });
                    if (match) {
                      const title = (match.friendly_name || match.client_name || match.filename || 'Recording').replace(/\.[a-z0-9]+$/i, '');
                      setDrafts((prev) => {
                        if (prev.some((d) => d.fileId === match.id)) return prev;
                        return prev.concat([{ id: `d_${match.id}`, title, fileId: match.id, transcript: transcriptReady ? 'ready' : 'processing', hint: (hint || filename || title) }]);
                      });
                    }
                  } catch {}
                  setActive(transcriptReady ? 'creator-finalize' : 'creator-upload');
                })();
              }}
            />
          )}
          {active === "settings" && <Settings token={token} />}
        </main>
      </div>
      
      {/* AI Assistant - Always available in bottom-right corner */}
      <AIAssistant token={token} user={user} />
    </div>
  );
}
