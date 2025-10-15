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
  const [distributionOpen, setDistributionOpen] = useState(false);
  const [distributionPodcast, setDistributionPodcast] = useState(null);
  const { toast } = useToast();
  const [me, setMe] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const profile = await makeApi(token).get('/api/auth/users/me');
        setMe(profile || null);
      } catch {}
    })();
  }, [token]);

  const getComplianceIssues = (p) => {
    const issues = [];
    const nameLen = (p?.name || '').trim().length;
    if (nameLen < 4) issues.push('name');
    if (!p?.podcast_type) issues.push('podcast_type');
    if (!p?.language) issues.push('language');
    if (!p?.contact_email) issues.push('contact_email');
    return issues;
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
                  ? `We only imported a preview of ${pendingImports[0].name}. Use "Import remaining episodes" to pull the rest.`
                  : `We only imported previews for ${pendingImports.length} shows. Use "Import remaining episodes" to complete the migration.`}
              </p>
            </div>
          )}
          {podcasts.length > 0 ? (
            <div className="space-y-6">
              {podcasts.map(podcast => {
                const issues = getComplianceIssues(podcast);
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
                        {podcast.cover_url ? (
                          <img
                            src={podcast.cover_url}
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
                          {issues.length === 0 && (
                            <ActionButton icon={Icons.Share2} onClick={() => openDistributionDialog(podcast)}>
                              Distribution checklist
                            </ActionButton>
                          )}
                          <ActionButton
                            icon={Icons.Trash2}
                            variant="destructive"
                            onClick={() => openDeleteDialog(podcast)}
                          >
                            Delete podcast
                          </ActionButton>
                        </div>
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
