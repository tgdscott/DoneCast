import { useEffect, useMemo, useState } from "react";
import * as Icons from "lucide-react";

import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/hooks/use-toast";
import { makeApi } from "@/lib/apiClient";

const STATUS_META = {
  not_started: { label: "Not started", badge: "secondary" },
  in_progress: { label: "In progress", badge: "outline" },
  completed: { label: "Completed", badge: "default" },
  skipped: { label: "Skipped", badge: "outline" },
};

const STATUS_OPTIONS = [
  { value: "not_started", label: "Not started" },
  { value: "in_progress", label: "In progress" },
  { value: "completed", label: "Completed" },
  { value: "skipped", label: "Skipped" },
];

const AUTOMATION_LABELS = {
  automatic: "Handled automatically",
  assisted: "Assisted submission",
  manual: "Manual submission",
};

const automationBadgeVariant = {
  automatic: "default",
  assisted: "secondary",
  manual: "outline",
};

function formatAutomationLabel(value) {
  if (!value) return "Manual submission";
  return AUTOMATION_LABELS[value] || value;
}

export default function DistributionChecklistDialog({ open, onOpenChange, podcast, token }) {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [items, setItems] = useState([]);
  const [notesDraft, setNotesDraft] = useState({});
  const [rssFeedUrl, setRssFeedUrl] = useState("");
  const [spreakerUrl, setSpreakerUrl] = useState("");
  const [savingKeys, setSavingKeys] = useState({});
  const [openKeys, setOpenKeys] = useState({});

  const podcastId = podcast?.id;

  useEffect(() => {
    if (!open) {
      return;
    }
    if (!token || !podcastId) {
      setItems([]);
      setNotesDraft({});
      setRssFeedUrl("");
      setSpreakerUrl("");
      return;
    }

    let aborted = false;
    setLoading(true);
    setError("");

    makeApi(token)
      .get(`/api/podcasts/${podcastId}/distribution/checklist`)
      .then((data) => {
        if (aborted) return;
        const list = Array.isArray(data?.items) ? data.items : [];
        setItems(list);
        setNotesDraft(Object.fromEntries(list.map((item) => [item.key, item.notes || ""])));
        setRssFeedUrl(data?.rss_feed_url || "");
        setSpreakerUrl(data?.spreaker_show_url || "");
      })
      .catch((err) => {
        if (aborted) return;
        const detail = err?.detail || err?.message || "Unable to load distribution checklist.";
        setError(detail);
      })
      .finally(() => {
        if (!aborted) {
          setLoading(false);
        }
      });

    return () => {
      aborted = true;
    };
  }, [open, token, podcastId]);

  const statusByKey = useMemo(() => Object.fromEntries(items.map((item) => [item.key, item.status])), [items]);

  const disabled = !podcastId || !token;

  const handleCopyFeed = async () => {
    if (!rssFeedUrl) return;
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(rssFeedUrl);
      } else {
        throw new Error("Clipboard API unavailable");
      }
      toast({ title: "RSS feed copied" });
    } catch (err) {
      toast({
        title: "Copy failed",
        description: err?.message || "Unable to copy RSS feed. Please copy it manually.",
        variant: "destructive",
      });
    }
  };

  const saveItem = async (key, body) => {
    if (!podcastId || !token) return;
    setSavingKeys((prev) => ({ ...prev, [key]: true }));
    try {
      const data = await makeApi(token).put(
        `/api/podcasts/${podcastId}/distribution/checklist/${encodeURIComponent(key)}`,
        body
      );
      setItems((prev) => prev.map((item) => (item.key === key ? data : item)));
      setNotesDraft((prev) => ({ ...prev, [key]: data?.notes || "" }));
      toast({ title: data?.name ? `${data.name} saved` : "Checklist updated" });
    } catch (err) {
      const detail = err?.detail || err?.message || "Unable to save changes.";
      toast({ title: "Save failed", description: detail, variant: "destructive" });
    } finally {
      setSavingKeys((prev) => {
        const next = { ...prev };
        delete next[key];
        return next;
      });
    }
  };

  const handleStatusChange = (key, newStatus) => {
    const notes = notesDraft[key] ?? "";
    saveItem(key, { status: newStatus, notes });
  };

  const handleSaveNotes = (key) => {
    const status = statusByKey[key] ?? "not_started";
    saveItem(key, { status, notes: notesDraft[key] ?? "" });
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          setError("");
        }
        onOpenChange?.(next);
      }}
    >
      <DialogContent className="max-w-4xl">
        <DialogHeader>
          <DialogTitle className="flex flex-col gap-1">
            <span>Distribute your podcast</span>
            {podcast?.name ? (
              <span className="text-base font-normal text-muted-foreground">{podcast.name}</span>
            ) : null}
          </DialogTitle>
          <DialogDescription className="space-y-3">
            <p>
              Work through the checklist below to submit your show to the major podcast directories. We provide direct links,
              instructions, and keep track of what has been completed.
            </p>
            {rssFeedUrl ? (
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <span className="font-medium">RSS feed:</span>
                <code className="rounded bg-muted px-2 py-1 text-xs break-all">{rssFeedUrl}</code>
                <Button type="button" variant="outline" size="sm" onClick={handleCopyFeed}>
                  <Icons.Clipboard className="mr-2 h-4 w-4" /> Copy
                </Button>
              </div>
            ) : (
              <div className="text-sm text-muted-foreground">
                Publish your first episode or link a Spreaker show to generate the RSS feed automatically.
              </div>
            )}
            {spreakerUrl ? (
              <div className="text-sm text-muted-foreground">
                Spreaker show URL: <a href={spreakerUrl} target="_blank" rel="noreferrer" className="text-primary underline">{spreakerUrl}</a>
              </div>
            ) : null}
          </DialogDescription>
        </DialogHeader>

        {error ? (
          <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </div>
        ) : null}

        {loading ? (
          <div className="flex items-center justify-center py-12 text-muted-foreground">
            <Icons.Loader2 className="mr-2 h-5 w-5 animate-spin" /> Loading distribution checklist…
          </div>
        ) : null}

        {!loading && !error ? (
          <div className="max-h-[65vh] space-y-4 overflow-y-auto pr-1">
            {items.map((item) => {
              const statusMeta = STATUS_META[item.status] || STATUS_META.not_started;
              const automationLabel = formatAutomationLabel(item.automation);
              const saving = Boolean(savingKeys[item.key]);
              const open = Boolean(openKeys[item.key]);
              return (
                <div key={item.key} className="rounded-lg border bg-card px-4 py-4 shadow-sm">
                  <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                    <div className="space-y-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="text-lg font-semibold">{item.name}</h3>
                        <Badge variant={statusMeta.badge}>{statusMeta.label}</Badge>
                        <Badge variant={automationBadgeVariant[item.automation] || "outline"}>{automationLabel}</Badge>
                      </div>
                      {item.summary ? <p className="text-sm text-muted-foreground">{item.summary}</p> : null}
                      {item.automation_notes ? (
                        <p className="text-xs text-muted-foreground">{item.automation_notes}</p>
                      ) : null}
                    </div>
                    <div className="flex flex-col items-start gap-2 md:items-end">
                      <button
                        type="button"
                        className="text-xs text-primary underline"
                        onClick={() => setOpenKeys((prev) => ({ ...prev, [item.key]: !open }))}
                      >
                        {open ? "Collapse" : "Expand"}
                      </button>
                      {item.action_label && item.action_url ? (
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          asChild
                          disabled={Boolean(item.disabled_reason)}
                        >
                          <a href={item.action_url} target="_blank" rel="noreferrer">
                            <Icons.ExternalLink className="mr-2 h-4 w-4" /> {item.action_label}
                          </a>
                        </Button>
                      ) : null}
                      {item.docs_url ? (
                        <a
                          href={item.docs_url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-xs text-primary underline"
                        >
                          Platform documentation
                        </a>
                      ) : null}
                    </div>
                  </div>

                  {item.disabled_reason ? (
                    <div className="mt-3 rounded-md border border-yellow-500/50 bg-yellow-500/10 px-3 py-2 text-sm text-yellow-900 dark:text-yellow-100">
                      {item.disabled_reason}
                    </div>
                  ) : null}

                  {open && Array.isArray(item.instructions) && item.instructions.length > 0 ? (
                    <ol className="mt-3 list-decimal space-y-1 pl-5 text-sm text-muted-foreground">
                      {item.instructions.map((step, idx) => (
                        <li key={idx}>{step}</li>
                      ))}
                    </ol>
                  ) : null}

                  {open && (
                  <div className="mt-4 grid gap-4 md:grid-cols-[minmax(0,220px)_minmax(0,1fr)] md:items-start">
                    <div className="space-y-2">
                      <Label htmlFor={`status-${item.key}`}>Status</Label>
                      <Select
                        value={item.status || "not_started"}
                        onValueChange={(value) => handleStatusChange(item.key, value)}
                        disabled={disabled}
                      >
                        <SelectTrigger id={`status-${item.key}`}>
                          <SelectValue placeholder="Select status" />
                        </SelectTrigger>
                        <SelectContent>
                          {STATUS_OPTIONS.map((option) => (
                            <SelectItem key={option.value} value={option.value}>
                              {option.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor={`notes-${item.key}`}>Notes</Label>
                      <Textarea
                        id={`notes-${item.key}`}
                        value={notesDraft[item.key] ?? ""}
                        onChange={(event) =>
                          setNotesDraft((prev) => ({ ...prev, [item.key]: event.target.value }))
                        }
                        placeholder="Add reminders or follow-up steps for your team"
                        rows={3}
                        disabled={disabled}
                      />
                      <div className="flex items-center justify-between text-xs text-muted-foreground">
                        <span>Only visible inside CloudPod.</span>
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          onClick={() => handleSaveNotes(item.key)}
                          disabled={disabled || saving}
                        >
                          {saving ? <Icons.Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                          Save notes
                        </Button>
                      </div>
                    </div>
                  </div>
                  )}
                </div>
              );
            })}

            {items.length === 0 ? (
              <div className="rounded-md border border-dashed border-muted px-4 py-8 text-center text-sm text-muted-foreground">
                No distribution destinations available yet.
              </div>
            ) : null}
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
