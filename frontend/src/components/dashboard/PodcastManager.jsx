import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import * as Icons from "lucide-react";
import { useState, useEffect } from "react";
import EditPodcastDialog from "./EditPodcastDialog";
import NewUserWizard from "./NewUserWizard";
import DistributionChecklistDialog from "./DistributionChecklistDialog";
import { useToast } from "@/hooks/use-toast";
import { makeApi, buildApiUrl } from "@/lib/apiClient";

const API_BASE_URL = ""; // Use relative so it works behind any proxy

export default function PodcastManager({ onBack, token, podcasts, setPodcasts }) {
  const [showToDelete, setShowToDelete] = useState(null);
  const [deleteConfirmationText, setDeleteConfirmationText] = useState("");
  const [isDeleting, setIsDeleting] = useState(false);
  const [isEditDialogOpen, setIsEditDialogOpen] = useState(false);
  const [podcastToEdit, setPodcastToEdit] = useState(null);
  const [isWizardOpen, setIsWizardOpen] = useState(false);
  const [recoveringId, setRecoveringId] = useState(null);
  const [publishingAllId, setPublishingAllId] = useState(null);
  const [distributionOpen, setDistributionOpen] = useState(false);
  const [distributionPodcast, setDistributionPodcast] = useState(null);
  const { toast } = useToast();
  const [isSpreakerConnected, setIsSpreakerConnected] = useState(false);
  const [me, setMe] = useState(null);
  const [episodeSummaryByPodcast, setEpisodeSummaryByPodcast] = useState({});
  const [linkingShowId, setLinkingShowId] = useState(null);
  const [creatingShowId, setCreatingShowId] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const profile = await makeApi(token).get('/api/auth/users/me');
        setMe(profile || null);
        setIsSpreakerConnected(!!profile?.spreaker_access_token);
      } catch { setIsSpreakerConnected(false); }
    })();
  }, [token]);

  // Fetch a tiny summary per podcast so we can decide whether to show "Publish All"
  useEffect(() => {
    if (!token || !podcasts || podcasts.length === 0) return;
    let aborted = false;
    (async () => {
      try {
        const api = makeApi(token);
        const entries = await Promise.all(
          podcasts.map(async (p) => {
            try {
              const s = await api.get(`/api/episodes/summary?podcast_id=${encodeURIComponent(p.id)}`);
              return [String(p.id), s];
            } catch {
              return [String(p.id), { total: 0, unpublished_or_unscheduled: 0 }];
            }
          })
        );
        if (!aborted) {
          const map = Object.fromEntries(entries);
          setEpisodeSummaryByPodcast(map);
        }
      } catch {}
    })();
    return () => { aborted = true; };
  }, [token, podcasts]);

  const getComplianceIssues = (p) => {
    const issues = [];
    const nameLen = (p?.name || '').trim().length;
    if (nameLen < 4) issues.push('name');
    if (!p?.podcast_type) issues.push('podcast_type');
    if (!p?.language) issues.push('language');
    if (!p?.contact_email) issues.push('contact_email');
    return issues;
  };

  const handlePublishToSpreaker = async (p) => {
    // If not connected, start OAuth then prompt user to return/retry
    try {
      if (!isSpreakerConnected) {
        const qs = new URLSearchParams({ access_token: token }).toString();
        const popupUrl = buildApiUrl(`/api/auth/spreaker/start?${qs}`);
        const popup = window.open(popupUrl, 'spreakerAuth', 'width=600,height=700');
        const timer = setInterval(async () => {
          if (!popup || popup.closed) {
            clearInterval(timer);
            try {
              const me = await makeApi(token).get('/api/auth/users/me');
              const connected = !!me?.spreaker_access_token;
              setIsSpreakerConnected(connected);
              if (connected) {
                toast({ title: 'Connected to Spreaker', description: 'You can now publish your podcast.' });
                // Open edit to review and save; a dedicated publish call can be added here once available
                openEditDialog(p);
              } else {
                toast({ title: 'Not connected', description: 'Please try connecting again.', variant: 'destructive' });
              }
            } catch {}
          }
        }, 1000);
        return;
      }
      // Connected: open edit to finalize details; integrate direct publish endpoint here if available.
      openEditDialog(p);
    } catch (e) {
      toast({ title: 'Unable to publish', description: e?.message || 'Please try again.', variant: 'destructive' });
    }
  };
  const rawFullpage = import.meta.env?.VITE_ONBOARDING_FULLPAGE ?? import.meta.env?.ONBOARDING_FULLPAGE;
  const fullPageOnboarding = rawFullpage === undefined ? true : String(rawFullpage).toLowerCase() === 'true';

  const openEditDialog = (podcast) => {
    setPodcastToEdit(podcast);
    setIsEditDialogOpen(true);
  };

  const closeEditDialog = () => {
    setPodcastToEdit(null);
    setIsEditDialogOpen(false);
  };

  const handleEditPodcast = (updatedPodcast) => {
    setPodcasts(prev => prev.map(p => p.id === updatedPodcast.id ? updatedPodcast : p));
    closeEditDialog();
  };

  const openDeleteDialog = (podcast) => {
    setShowToDelete(podcast);
    setDeleteConfirmationText("");
  };

  const closeDeleteDialog = () => {
    setShowToDelete(null);
  };

  const openWizard = () => {
    // If full-page onboarding is enabled, steer users to /onboarding instead of opening the modal
    if (fullPageOnboarding) {
      try { window.location.href = '/onboarding?from=manager&reset=1'; } catch {}
    } else {
      setIsWizardOpen(true);
    }
  };

  const handlePodcastCreated = (newPodcast) => {
    setPodcasts(prev => [newPodcast, ...prev]);
    setIsWizardOpen(false);
  };

  const handleDeleteShow = async () => {
    if (!showToDelete) return;
    setIsDeleting(true);
    try {
      const response = await fetch(buildApiUrl(`/api/podcasts/${showToDelete.id}`), {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (!response.ok) {
        throw new Error("Failed to delete the show.");
      }

      setPodcasts(prev => prev.filter(p => p.id !== showToDelete.id));
      toast({ title: "Success", description: `Show "${showToDelete.name}" has been deleted.` });
      closeDeleteDialog();

    } catch (err) {
      toast({ title: "Error", description: err.message, variant: "destructive" });
    } finally {
      setIsDeleting(false);
    }
  };

  const openDistributionDialog = (podcast) => {
    setDistributionPodcast(podcast);
    setDistributionOpen(true);
  };

  const handleDistributionOpenChange = (open) => {
    setDistributionOpen(open);
    if (!open) {
      setDistributionPodcast(null);
    }
  };

  const handleRecovery = async (podcast) => {
    if (!podcast || !podcast.id) return;
    if (!window.confirm(`This will scan Spreaker for episodes belonging to "${podcast.name}" and create local records for any that are missing. This cannot be undone. Continue?`)) {
      return;
    }

    setRecoveringId(podcast.id);
    try {
      const api = makeApi(token);
      const result = await api.post(`/api/podcasts/${podcast.id}/recover-from-spreaker`);
      
      const count = result?.recovered_count || 0;
      if (count > 0) {
        toast({
          title: "Recovery Complete",
          description: `Successfully recovered and created records for ${count} missing episodes. Please refresh the episode history to see them.`,
        });
      } else {
        toast({
          title: "Scan Complete",
          description: "No missing episodes were found on Spreaker for this show.",
        });
      }
    } catch (error) {
      const detail = error?.detail || error?.message || "An unknown error occurred.";
      toast({
        variant: 'destructive',
        title: 'Recovery Failed',
        description: detail,
      });
    } finally {
      setRecoveringId(null);
    }
  };

  const handlePublishAll = async (podcast, opts = {}) => {
    if (!podcast || !podcast.id) return;
    const summary = episodeSummaryByPodcast[String(podcast.id)] || { unpublished_or_unscheduled: 0 };
    const eligible = summary.unpublished_or_unscheduled || 0;
    if (eligible < 2) {
      toast({ title: 'Nothing to publish', description: 'There are fewer than 2 unpublished or unscheduled episodes.' });
      return;
    }
    if (!window.confirm(`Publish ${eligible} episode(s) from "${podcast.name}" to Spreaker now?`)) {
      return;
    }
    setPublishingAllId(podcast.id);
    try {
      const api = makeApi(token);
      const body = { publish_state: opts.publish_state || 'public', include_already_linked: false };
      const res = await api.post(`/api/podcasts/${podcast.id}/publish-all`, body);
      const started = res?.started ?? 0;
      const skipped = (res?.skipped_no_audio ?? 0) + (res?.skipped_already_linked ?? 0);
      toast({ title: 'Batch publish enqueued', description: `Started ${started}. Skipped ${skipped}. Errors ${res?.errors ?? 0}.` });
    } catch (error) {
      const detail = error?.detail || error?.message || 'Failed to start batch publish.';
      toast({ variant: 'destructive', title: 'Publish All failed', description: detail });
    } finally {
      setPublishingAllId(null);
    }
  };

  const handleLinkSpreakerShow = async (podcast) => {
    if (!podcast) return;
    const val = window.prompt('Enter existing Spreaker show ID (numeric):');
    if (!val) return;
    if (!/^[0-9]+$/.test(val)) { toast({ variant: 'destructive', title:'Invalid show id', description:'Must be numeric.'}); return; }
    setLinkingShowId(podcast.id);
    try {
      const api = makeApi(token);
      const res = await api.post(`/api/podcasts/${podcast.id}/link-spreaker-show`, { show_id: String(val) });
      const updated = res?.podcast || { ...podcast, spreaker_show_id: String(val) };
      setPodcasts(prev => prev.map(p => p.id === podcast.id ? updated : p));
      toast({ title: 'Linked', description: 'Spreaker show linked successfully.' });
    } catch (e) {
      toast({ variant: 'destructive', title:'Failed to link', description: e?.detail || e?.message || 'Please try again.' });
    } finally { setLinkingShowId(null); }
  };

  const handleCreateSpreakerShow = async (podcast) => {
    if (!podcast) return;
    if (!isSpreakerConnected) {
      toast({ variant:'destructive', title:'Not connected', description:'Connect Spreaker first.' });
      return;
    }
    if (!window.confirm(`Create a new Spreaker show for "${podcast.name}"?`)) return;
    setCreatingShowId(podcast.id);
    try {
      const api = makeApi(token);
      const res = await api.post(`/api/podcasts/${podcast.id}/create-spreaker-show`, {
        title: podcast.name,
        description: podcast.description || '',
        language: podcast.language || 'en'
      });
      const updated = res?.podcast || podcast;
      setPodcasts(prev => prev.map(p => p.id === podcast.id ? updated : p));
      toast({ title: 'Show created', description: `Linked Spreaker show ${res?.spreaker_show_id || ''}` });
    } catch (e) {
      toast({ variant: 'destructive', title:'Failed to create show', description: e?.detail || e?.message || 'Please try again.' });
    } finally { setCreatingShowId(null); }
  };

  return (
    <div className="p-6">
  <Button onClick={onBack} variant="ghost" className="mb-4"><Icons.ArrowLeft className="w-4 h-4 mr-2" />Back to Dashboard</Button>
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-3">
            <div>
              <CardTitle>Manage Your Podcasts</CardTitle>
              <CardDescription>Here you can create, import, edit, or delete your podcasts.</CardDescription>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={openWizard}><Icons.Plus className="w-4 h-4 mr-2" /> New Podcast</Button>
              <Button variant="outline" size="sm" onClick={() => {
                try { window.dispatchEvent(new CustomEvent('ppp:navigate-view', { detail: 'rssImporter' })); } catch {}
              }}><Icons.Rss className="w-4 h-4 mr-2" /> Import</Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {podcasts.length > 0 ? (
            <div className="space-y-4">
              {podcasts.map(podcast => (
                <Card key={podcast.id} className="flex items-center justify-between p-4">
                  <div className="flex items-center gap-4">
                    {podcast.cover_path ? (
                      <img
                        src={
                          podcast.cover_path.startsWith('http')
                            ? podcast.cover_path
                            : `/static/media/${podcast.cover_path.replace(/^\/+/, '').split('/').pop()}`
                        }
                        alt={`${podcast.name} cover`}
                        className="w-16 h-16 rounded-md object-cover"
                        onError={(e)=>{e.currentTarget.style.display='none'; const sib=e.currentTarget.nextSibling; if(sib) sib.style.display='flex';}}
                      />
                    ) : (
                      <div className="w-16 h-16 rounded-md bg-gray-100 flex items-center justify-center">
                        <Icons.Image className="w-8 h-8 text-gray-400" />
                      </div>
                    )}
                    <div>
                      <h3 className="font-semibold">{podcast.name}</h3>
                      <p className="text-sm text-gray-500 line-clamp-2">{podcast.description || "No description."}</p>
                    </div>
                  </div>
                  <div className="flex items-center space-x-2">
                    <Button variant="outline" size="sm" onClick={() => openDistributionDialog(podcast)}>
                      <Icons.Share2 className="w-4 h-4 mr-2" /> Distribution
                    </Button>
                    {/* Spreaker publish/setup pills */}
                    {(() => {
                      const issues = getComplianceIssues(podcast);
                      const hasShowId = !!podcast.spreaker_show_id;
                      // Only one pill at a time.
                      // Rule: Yellow requires a Spreaker ID (i.e., show exists on Spreaker) but is incomplete locally
                      if (hasShowId && issues.length > 0) {
                        return (
                          <button
                            className="px-3 py-1 rounded-full bg-yellow-400 text-black text-xs"
                            onClick={() => openEditDialog(podcast)}
                          >
                            Complete setup to publish to Spreaker
                          </button>
                        );
                      }
                      // If not connected and no Spreaker show yet, offer green publish CTA when compliant
                      if (!isSpreakerConnected && !hasShowId && issues.length === 0) {
                        return (
                          <button
                            className="px-3 py-1 rounded-full bg-green-600 text-white text-xs"
                            onClick={() => handlePublishToSpreaker(podcast)}
                          >
                            Publish to Spreaker
                          </button>
                        );
                      }
                      // Otherwise, no pill for non-Spreaker shows or when fully compliant with ID
                      return null;
                    })()}
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon" aria-label={`Actions for ${podcast.name}`}>
                          <Icons.Settings className="h-5 w-5" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem
                          onClick={() => handleRecovery(podcast)}
                          disabled={recoveringId === podcast.id || !podcast.spreaker_show_id}
                        >
                        {/* Link/Create Spreaker show helpers */}
                        {!podcast.spreaker_show_id && (
                          <DropdownMenuItem onClick={() => handleLinkSpreakerShow(podcast)} disabled={linkingShowId === podcast.id}>
                            {linkingShowId === podcast.id ? (
                              <Icons.Loader2 className="w-4 h-4 mr-2 animate-spin" />
                            ) : (
                              <Icons.Link2 className="w-4 h-4 mr-2" />
                            )}
                            <span>Link existing Spreaker Show…</span>
                          </DropdownMenuItem>
                        )}
                        {!podcast.spreaker_show_id && isSpreakerConnected && (
                          <DropdownMenuItem onClick={() => handleCreateSpreakerShow(podcast)} disabled={creatingShowId === podcast.id}>
                            {creatingShowId === podcast.id ? (
                              <Icons.Loader2 className="w-4 h-4 mr-2 animate-spin" />
                            ) : (
                              <Icons.Plus className="w-4 h-4 mr-2" />
                            )}
                            <span>Create Spreaker Show</span>
                          </DropdownMenuItem>
                        )}
                          {recoveringId === podcast.id ? (
                            <Icons.Loader2 className="w-4 h-4 mr-2 animate-spin" />
                          ) : (
                            <Icons.RefreshCw className="w-4 h-4 mr-2" />
                          )}
                          <span>Recover Missing Episodes</span>
                        </DropdownMenuItem>
                        {(() => {
                          const summary = episodeSummaryByPodcast[String(podcast.id)] || { unpublished_or_unscheduled: 0 };
                          const eligible = summary.unpublished_or_unscheduled || 0;
                          const canShow = isSpreakerConnected && !!podcast.spreaker_show_id && eligible >= 2;
                          if (!canShow) return null;
                          return (
                            <DropdownMenuItem
                              onClick={() => handlePublishAll(podcast)}
                              disabled={publishingAllId === podcast.id}
                            >
                              {publishingAllId === podcast.id ? (
                                <Icons.Loader2 className="w-4 h-4 mr-2 animate-spin" />
                              ) : (
                                <Icons.Send className="w-4 h-4 mr-2" />
                              )}
                              <span>Publish All to Spreaker</span>
                            </DropdownMenuItem>
                          );
                        })()}
                      </DropdownMenuContent>
                    </DropdownMenu>
                    <Button variant="outline" size="sm" onClick={() => openEditDialog(podcast)}>Edit</Button>
                    <Button variant="destructive" size="sm" onClick={() => openDeleteDialog(podcast)}>
                      <Icons.Trash2 className="w-4 h-4 mr-2" /> Delete
                    </Button>
                  </div>
                </Card>
              ))}
            </div>
          ) : (
      <div className="text-center py-10">
    <p className="mb-4">You haven't created any podcasts yet.</p>
        <Button onClick={openWizard}>
          <Plus className="w-4 h-4 mr-2" /> {fullPageOnboarding ? 'Get started' : 'Create Your First Show'}
        </Button>
      </div>
          )}
        </CardContent>
      </Card>

      {/* Delete Confirmation Dialog */}
      <Dialog open={!!showToDelete} onOpenChange={closeDeleteDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Are you absolutely sure?</DialogTitle>
            <DialogDescription>
              This action cannot be undone. This will permanently delete the podcast
              <strong className="text-red-600"> "{showToDelete?.name}" </strong>
              and all of its associated episodes.
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <Label htmlFor="delete-confirm">Please type <strong className="text-red-600">delete</strong> to confirm.</Label>
            <Input 
              id="delete-confirm"
              value={deleteConfirmationText}
              onChange={(e) => setDeleteConfirmationText(e.target.value)}
              className="mt-2"
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={closeDeleteDialog}>Cancel</Button>
            <Button
              variant="destructive"
              disabled={deleteConfirmationText !== 'delete' || isDeleting}
              onClick={handleDeleteShow}
            >
              {isDeleting ? <Icons.Loader2 className="w-4 h-4 animate-spin" /> : "Delete Podcast"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Podcast Dialog */}
      {isEditDialogOpen && podcastToEdit && (
        <EditPodcastDialog
          isOpen={isEditDialogOpen}
          onClose={closeEditDialog}
          podcast={podcastToEdit}
          onSave={handleEditPodcast}
          token={token}
          userEmail={me?.email || podcastToEdit?.user?.email || undefined}
          userFirstName={me?.first_name}
          userLastName={me?.last_name}
        />
      )}

      {/* New User Wizard (fallback, behind feature flag) */}
      {!fullPageOnboarding && (
        <NewUserWizard
          open={isWizardOpen}
          onOpenChange={setIsWizardOpen}
          token={token}
          onPodcastCreated={handlePodcastCreated}
        />
      )}

      <DistributionChecklistDialog
        open={distributionOpen}
        onOpenChange={handleDistributionOpenChange}
        podcast={distributionPodcast}
        token={token}
      />
    </div>
  );
}
