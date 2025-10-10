import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import * as Icons from "lucide-react";
import { useState, useEffect } from "react";
import EditPodcastDialog from "./EditPodcastDialog";
import NewUserWizard from "./NewUserWizard";
import DistributionChecklistDialog from "./DistributionChecklistDialog";
import { useToast } from "@/hooks/use-toast";
import { makeApi, buildApiUrl } from "@/lib/apiClient";

const API_BASE_URL = ""; // Use relative so it works behind any proxy

export default function PodcastManager({ onBack, token, podcasts, setPodcasts, onViewAnalytics }) {
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
    const needsFullImport = !!podcast?.import_status?.needs_full_import;
    const actionText = needsFullImport ? 'import the remaining episodes from Spreaker' : 'scan Spreaker for missing episodes';
    if (!window.confirm(`We will ${actionText} for "${podcast.name}". Continue?`)) {
      return;
    }

    setRecoveringId(podcast.id);
    try {
      const api = makeApi(token);
      const result = await api.post(`/api/podcasts/${podcast.id}/recover-from-spreaker`);
      
      const count = result?.recovered_count || 0;
      if (count > 0) {
        toast({
          title: needsFullImport ? "Import complete" : "Recovery complete",
          description: needsFullImport
            ? `Imported ${count} additional episode${count === 1 ? '' : 's'} from Spreaker. The rest of your library is now available locally.`
            : `Successfully recovered and created records for ${count} missing episodes. Please refresh the episode history to see them.`,
        });
      } else {
        toast({
          title: "Scan Complete",
          description: "No missing episodes were found on Spreaker for this show.",
        });
      }
      if (result?.import_status) {
        setPodcasts(prev => prev.map(p => p.id === podcast.id ? { ...p, import_status: result.import_status } : p));
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

  const ActionButton = ({ icon: IconEl, children, className = "", variant = "outline", ...props }) => (
    <Button variant={variant} className={`w-full justify-start ${className}`} {...props}>
      {IconEl ? <IconEl className="w-4 h-4 mr-2" /> : null}
      {children}
    </Button>
  );

  const pendingImports = podcasts.filter(p => p?.import_status?.needs_full_import);

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
        <CardContent className="space-y-6">
          {pendingImports.length > 0 && (
            <div className="rounded-lg border border-border bg-muted/40 p-4 text-sm space-y-1">
              <p className="font-medium text-foreground">Finish importing your back catalogue</p>
              <p className="text-muted-foreground">
                {pendingImports.length === 1
                  ? `We only imported a preview of ${pendingImports[0].name}. Link the show to Spreaker and use “Import remaining episodes” to pull the rest.`
                  : `We only imported previews for ${pendingImports.length} shows. Link them to Spreaker and use “Import remaining episodes” to complete the migration.`}
              </p>
            </div>
          )}
          {podcasts.length > 0 ? (
            <div className="space-y-6">
              {podcasts.map(podcast => {
                const issues = getComplianceIssues(podcast);
                const hasShowId = !!podcast.spreaker_show_id;
                const importStatus = podcast.import_status || null;
                const needsFullImport = !!importStatus?.needs_full_import;
                const importedCount = importStatus?.imported_count ?? 0;
                const feedTotal = importStatus?.feed_total ?? 0;
                const previewSummary = needsFullImport && feedTotal
                  ? `${Math.min(importedCount, feedTotal)} of ${feedTotal} episodes imported in preview`
                  : null;
                return (
                  <Card key={podcast.id} className="p-6">
                    <div className="flex flex-col lg:flex-row gap-6">
                      <div className="flex gap-4 lg:w-1/2">
                        {podcast.cover_path ? (
                          <img
                            src={
                              podcast.cover_path.startsWith('http')
                                ? podcast.cover_path
                                : `/static/media/${podcast.cover_path.replace(/^\/+/, '').split('/').pop()}`
                            }
                            alt={`${podcast.name} cover`}
                            className="w-24 h-24 rounded-md object-cover"
                            onError={(e)=>{e.currentTarget.style.display='none'; const sib=e.currentTarget.nextSibling; if(sib) sib.style.display='flex';}}
                          />
                        ) : (
                          <div className="w-24 h-24 rounded-md bg-gray-100 flex items-center justify-center">
                            <Icons.Image className="w-10 h-10 text-gray-400" />
                          </div>
                        )}
                        <div className="space-y-2">
                          <div className="flex items-center gap-2 flex-wrap">
                            <h3 className="font-semibold text-lg">{podcast.name}</h3>
                            {hasShowId && <Badge variant="secondary">Linked to Spreaker</Badge>}
                            {needsFullImport && <Badge variant="outline" className="border-amber-500 text-amber-700 bg-amber-50">Preview only</Badge>}
                          </div>
                          {previewSummary && (
                            <p className="text-sm text-amber-700 flex items-center gap-2"><Icons.AlertTriangle className="w-4 h-4" /> {previewSummary}</p>
                          )}
                          <p className="text-sm text-muted-foreground leading-relaxed max-w-xl">{podcast.description || "No description."}</p>
                        </div>
                      </div>
                      <div className="flex-1 space-y-4">
                        <div className="grid sm:grid-cols-2 gap-3">
                          <ActionButton icon={Icons.Settings} onClick={() => openEditDialog(podcast)}>Edit show details</ActionButton>
                          {onViewAnalytics && (
                            <ActionButton icon={Icons.BarChart3} onClick={() => onViewAnalytics(podcast.id)}>
                              View Analytics
                            </ActionButton>
                          )}
                          {(issues.length === 0 || hasShowId) && (
                            <ActionButton icon={Icons.Share2} onClick={() => openDistributionDialog(podcast)}>
                              Distribution checklist
                            </ActionButton>
                          )}
                          {!hasShowId && (
                            <ActionButton
                              icon={Icons.Link2}
                              onClick={() => handleLinkSpreakerShow(podcast)}
                              disabled={linkingShowId === podcast.id}
                            >
                              {linkingShowId === podcast.id ? 'Linking…' : 'Link existing Spreaker show'}
                            </ActionButton>
                          )}
                          {!isSpreakerConnected && issues.length === 0 && (
                            <ActionButton
                              icon={Icons.Radio}
                              onClick={() => handlePublishToSpreaker(podcast)}
                            >
                              Connect to Spreaker to publish
                            </ActionButton>
                          )}
                          {!hasShowId && isSpreakerConnected && (
                            <ActionButton
                              icon={Icons.Plus}
                              onClick={() => handleCreateSpreakerShow(podcast)}
                              disabled={creatingShowId === podcast.id}
                            >
                              {creatingShowId === podcast.id ? 'Creating…' : 'Create new Spreaker show'}
                            </ActionButton>
                          )}
                          {needsFullImport && (
                            <ActionButton
                              icon={Icons.DownloadCloud}
                              onClick={() => handleRecovery(podcast)}
                              disabled={recoveringId === podcast.id || !podcast.spreaker_show_id}
                            >
                              {recoveringId === podcast.id ? 'Importing remaining episodes…' : 'Import remaining episodes'}
                            </ActionButton>
                          )}
                          {!needsFullImport && hasShowId && (
                            <ActionButton
                              icon={Icons.RefreshCw}
                              onClick={() => handleRecovery(podcast)}
                              disabled={recoveringId === podcast.id}
                            >
                              {recoveringId === podcast.id ? 'Scanning Spreaker…' : 'Recover missing episodes'}
                            </ActionButton>
                          )}
                          {(() => {
                            const summary = episodeSummaryByPodcast[String(podcast.id)] || { unpublished_or_unscheduled: 0 };
                            const eligible = summary.unpublished_or_unscheduled || 0;
                            const canShow = isSpreakerConnected && hasShowId && eligible >= 2;
                            if (!canShow) return null;
                            return (
                              <ActionButton
                                icon={Icons.Send}
                                onClick={() => handlePublishAll(podcast)}
                                disabled={publishingAllId === podcast.id}
                              >
                                {publishingAllId === podcast.id ? 'Publishing…' : `Publish ${eligible} episodes to Spreaker`}
                              </ActionButton>
                            );
                          })()}
                          <ActionButton
                            icon={Icons.Trash2}
                            variant="destructive"
                            onClick={() => openDeleteDialog(podcast)}
                          >
                            Delete podcast
                          </ActionButton>
                        </div>
                        {!hasShowId && issues.length === 0 && !isSpreakerConnected && (
                          <p className="text-sm text-muted-foreground">
                            Ready to publish? Connect your Spreaker account first so we can push episodes over automatically.
                          </p>
                        )}
                      </div>
                    </div>
                  </Card>
                );
              })}
            </div>
          ) : (
            <div className="text-center py-10">
              <p className="mb-4">You haven't created any podcasts yet.</p>
              <Button onClick={openWizard}>
                <Icons.Plus className="w-4 h-4 mr-2" /> {fullPageOnboarding ? 'Get started' : 'Create Your First Show'}
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
