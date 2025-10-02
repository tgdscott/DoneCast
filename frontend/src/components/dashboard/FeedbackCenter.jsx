import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  Loader2,
  MessageCircle,
  MessageSquarePlus,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";

import { makeApi, coerceArray } from "@/lib/apiClient";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const TYPE_LABELS = {
  feature: "Feature Request",
  bug: "Bug Report",
  other: "Other",
};

const STATUS_LABELS = {
  open: "Open",
  in_progress: "In Progress",
  closed: "Closed",
};

const STATUS_BADGES = {
  open: "bg-blue-100 text-blue-800",
  in_progress: "bg-amber-100 text-amber-800",
  closed: "bg-emerald-100 text-emerald-800",
};

const STATUS_OPTIONS = [
  { value: "open", label: "Mark Open" },
  { value: "in_progress", label: "Mark In Progress" },
  { value: "closed", label: "Mark Closed" },
];

const TYPE_TABS = [
  { value: "all", label: "All" },
  { value: "feature", label: "Features" },
  { value: "bug", label: "Bugs" },
  { value: "other", label: "Other" },
];

function formatRelativeTime(iso) {
  if (!iso) return "";
  try {
    const value = new Date(iso);
    const diffMs = Date.now() - value.getTime();
    const diffSec = Math.floor(diffMs / 1000);
    if (diffSec < 60) return "just now";
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `${diffHr}h ago`;
    const diffDay = Math.floor(diffHr / 24);
    if (diffDay < 30) return `${diffDay}d ago`;
    const diffMonth = Math.floor(diffDay / 30);
    if (diffMonth < 12) return `${diffMonth}mo ago`;
    const diffYear = Math.floor(diffMonth / 12);
    return `${diffYear}y ago`;
  } catch {
    return "";
  }
}

function formatFullDate(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export default function FeedbackCenter({ token, onBack, currentUser, canModerate }) {
  const { toast } = useToast();
  const [items, setItems] = useState([]);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [selectedType, setSelectedType] = useState("all");
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState(null);
  const [newItem, setNewItem] = useState({ type: "feature", title: "", body: "" });
  const [formError, setFormError] = useState(null);
  const [creating, setCreating] = useState(false);
  const [commentText, setCommentText] = useState("");
  const [commentError, setCommentError] = useState(null);
  const [commentSubmitting, setCommentSubmitting] = useState(false);
  const [statusUpdating, setStatusUpdating] = useState(false);
  const [voteBusy, setVoteBusy] = useState(false);

  const applyDetailToList = useCallback((item) => {
    if (!item) return;
    setItems((prev) => {
      const filtered = Array.isArray(prev) ? prev.filter((existing) => existing.id !== item.id) : [];
      const merged = [item, ...filtered];
      merged.sort((a, b) => {
        const aTime = new Date(a.created_at || 0).getTime();
        const bTime = new Date(b.created_at || 0).getTime();
        return bTime - aTime;
      });
      return merged;
    });
  }, []);

  const loadList = useCallback(
    async (opts = { silent: false }) => {
      if (!token) return [];
      const api = makeApi(token);
      if (opts.silent) {
        setRefreshing(true);
      } else {
        setListLoading(true);
        setListError(null);
      }
      try {
        const data = await api.get("/api/feedback/");
        const list = coerceArray(data);
        setItems(list);
        setListError(null);
        return list;
      } catch (err) {
        const message = err?.detail || err?.message || "Unable to load feedback right now.";
        setListError(message);
        if (!opts.silent) {
          setItems([]);
        }
        return [];
      } finally {
        if (opts.silent) {
          setRefreshing(false);
        } else {
          setListLoading(false);
        }
      }
    },
    [token]
  );

  const loadDetail = useCallback(
    async (id) => {
      if (!token || !id) return null;
      const api = makeApi(token);
      setDetailLoading(true);
      setDetailError(null);
      try {
        const data = await api.get(`/api/feedback/${id}`);
        setDetail(data);
        setDetailError(null);
        return data;
      } catch (err) {
        const message = err?.detail || err?.message || "Unable to load that feedback item.";
        setDetail(null);
        setDetailError(message);
        return null;
      } finally {
        setDetailLoading(false);
      }
    },
    [token]
  );

  useEffect(() => {
    loadList();
  }, [loadList]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      setDetailError(null);
      return;
    }
    loadDetail(selectedId);
  }, [selectedId, loadDetail]);

  const filteredItems = useMemo(() => {
    if (selectedType === "all") return items;
    return items.filter((item) => item.type === selectedType);
  }, [items, selectedType]);

  useEffect(() => {
    if (filteredItems.length === 0) {
      return;
    }
    if (!selectedId || !filteredItems.some((item) => item.id === selectedId)) {
      setSelectedId(filteredItems[0].id);
    }
  }, [filteredItems, selectedId]);

  const handleCreate = async (event) => {
    event.preventDefault();
    if (!token) return;
    const title = (newItem.title || "").trim();
    const body = (newItem.body || "").trim();
    if (title.length < 3 || body.length < 10) {
      setFormError("Please provide a short title and a bit more detail.");
      return;
    }
    setFormError(null);
    setCreating(true);
    try {
      const api = makeApi(token);
      const payload = { type: newItem.type, title, body };
      const created = await api.post("/api/feedback/", payload);
      applyDetailToList(created);
      setDetail(created);
      setSelectedType(created.type || newItem.type);
      setSelectedId(created.id);
      setNewItem((prev) => ({ ...prev, title: "", body: "" }));
      toast({ title: "Feedback submitted", description: "Thanks for letting us know!" });
    } catch (err) {
      const message = err?.detail || err?.message || "Unable to submit feedback right now.";
      setFormError(message);
    } finally {
      setCreating(false);
    }
  };

  const canUpdateStatus = detail && (canModerate || detail.user_id === currentUser?.id);

  const handleStatusChange = async (status) => {
    if (!detail || !token) return;
    if (detail.status === status) return;
    setStatusUpdating(true);
    try {
      const api = makeApi(token);
      const updated = await api.patch(`/api/feedback/${detail.id}`, { status });
      applyDetailToList(updated);
      setDetail(updated);
      toast({ title: "Status updated", description: `Marked as ${STATUS_LABELS[status] || status}.` });
    } catch (err) {
      const message = err?.detail || err?.message || "Unable to update the status.";
      toast({ title: "Update failed", description: message, variant: "destructive" });
    } finally {
      setStatusUpdating(false);
    }
  };

  const handleAddComment = async (event) => {
    event.preventDefault();
    if (!detail || !token) return;
    const trimmed = (commentText || "").trim();
    if (trimmed.length < 2) {
      setCommentError("Add a bit more detail to your comment.");
      return;
    }
    setCommentError(null);
    setCommentSubmitting(true);
    try {
      const api = makeApi(token);
      const updated = await api.post(`/api/feedback/${detail.id}/comments`, { body: trimmed });
      applyDetailToList(updated);
      setDetail(updated);
      setCommentText("");
      toast({ title: "Comment posted" });
    } catch (err) {
      const message = err?.detail || err?.message || "Unable to add your comment.";
      setCommentError(message);
    } finally {
      setCommentSubmitting(false);
    }
  };

  const handleVote = async (value) => {
    if (!detail || !token) return;
    if (detail.type !== "feature") return;
    const desired = detail.user_vote === value ? 0 : value;
    setVoteBusy(true);
    try {
      const api = makeApi(token);
      const updated = await api.post(`/api/feedback/${detail.id}/vote`, { value: desired });
      applyDetailToList(updated);
      setDetail(updated);
    } catch (err) {
      const message = err?.detail || err?.message || "Unable to record your vote.";
      toast({ title: "Vote failed", description: message, variant: "destructive" });
    } finally {
      setVoteBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <Button
        variant="ghost"
        className="px-0 w-auto text-slate-600 hover:text-slate-800"
        onClick={onBack}
      >
        <ArrowLeft className="w-4 h-4 mr-2" />
        Back to dashboard
      </Button>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-1">
          <Card className="border border-slate-200 shadow-sm">
            <CardHeader>
              <CardTitle>Share feedback</CardTitle>
              <CardDescription>Report issues or suggest features we should build next.</CardDescription>
            </CardHeader>
            <CardContent>
              <form className="space-y-4" onSubmit={handleCreate}>
                <div className="space-y-2">
                  <label className="text-sm font-medium text-slate-600" htmlFor="feedback-type">Type</label>
                  <Select
                    value={newItem.type}
                    onValueChange={(value) => setNewItem((prev) => ({ ...prev, type: value }))}
                  >
                    <SelectTrigger id="feedback-type">
                      <SelectValue placeholder="Select type" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="feature">Feature Request</SelectItem>
                      <SelectItem value="bug">Bug Report</SelectItem>
                      <SelectItem value="other">General Feedback</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium text-slate-600" htmlFor="feedback-title">Title</label>
                  <Input
                    id="feedback-title"
                    placeholder="Give it a quick headline"
                    value={newItem.title}
                    onChange={(event) => setNewItem((prev) => ({ ...prev, title: event.target.value }))}
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium text-slate-600" htmlFor="feedback-body">Details</label>
                  <Textarea
                    id="feedback-body"
                    rows={5}
                    placeholder="What happened? What would you love to see?"
                    value={newItem.body}
                    onChange={(event) => setNewItem((prev) => ({ ...prev, body: event.target.value }))}
                  />
                </div>
                {formError && <p className="text-sm text-red-600">{formError}</p>}
                <Button type="submit" disabled={creating} className="w-full md:w-auto">
                  {creating ? (
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  ) : (
                    <MessageSquarePlus className="w-4 h-4 mr-2" />
                  )}
                  Submit feedback
                </Button>
              </form>
            </CardContent>
          </Card>

          <Card className="border border-slate-200 shadow-sm">
            <CardHeader className="space-y-1">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <CardTitle>Feedback backlog</CardTitle>
                  <CardDescription>Browse requests and reports from the community.</CardDescription>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => loadList({ silent: true })}
                  disabled={listLoading || refreshing}
                >
                  {refreshing ? <Loader2 className="w-4 h-4 animate-spin" /> : "Refresh"}
                </Button>
              </div>
              <Tabs value={selectedType} onValueChange={(value) => { setSelectedType(value); setSelectedId(null); }}>
                <TabsList className="grid grid-cols-4 gap-1 mt-4">
                  {TYPE_TABS.map((tab) => (
                    <TabsTrigger key={tab.value} value={tab.value} className="text-xs">
                      {tab.label}
                    </TabsTrigger>
                  ))}
                </TabsList>
              </Tabs>
            </CardHeader>
            <CardContent className="space-y-2">
              {listLoading ? (
                <div className="flex items-center gap-2 text-sm text-slate-500">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Loading feedback…
                </div>
              ) : listError ? (
                <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
                  {listError}
                </div>
              ) : filteredItems.length === 0 ? (
                <div className="rounded-md border border-dashed border-slate-200 bg-slate-50 p-4 text-center text-sm text-slate-500">
                  No feedback items in this category yet.
                </div>
              ) : (
                <div className="space-y-2">
                  {filteredItems.map((item) => (
                    <button
                      type="button"
                      key={item.id}
                      onClick={() => setSelectedId(item.id)}
                      className={cn(
                        "w-full rounded-md border p-3 text-left transition",
                        selectedId === item.id
                          ? "border-blue-400 bg-blue-50"
                          : "border-transparent bg-white hover:bg-slate-50"
                      )}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="space-y-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="font-medium text-slate-800">{item.title}</span>
                            <Badge variant="secondary" className="text-[10px] uppercase tracking-wide">
                              {TYPE_LABELS[item.type] || item.type}
                            </Badge>
                          </div>
                          <p className="text-xs text-slate-500 line-clamp-2">{item.body}</p>
                        </div>
                        <Badge className={cn("text-[10px] uppercase tracking-wide", STATUS_BADGES[item.status] || "bg-slate-100 text-slate-700") }>
                          {STATUS_LABELS[item.status] || item.status}
                        </Badge>
                      </div>
                      <div className="mt-2 flex flex-wrap items-center gap-4 text-xs text-slate-500">
                        <span>{formatRelativeTime(item.created_at)}</span>
                        <span className="flex items-center gap-1">
                          <MessageCircle className="w-3 h-3" />
                          {item.comment_count}
                        </span>
                        <span className="flex items-center gap-1">
                          <ThumbsUp className="w-3 h-3" />
                          {item.upvotes}
                        </span>
                        <span className="flex items-center gap-1">
                          <ThumbsDown className="w-3 h-3" />
                          {item.downvotes}
                        </span>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        <div className="lg:col-span-2">
          <Card className="border border-slate-200 shadow-sm">
            <CardHeader className="space-y-3">
              <CardTitle>Feedback details</CardTitle>
              <CardDescription>
                Collaborate on requests, log progress, and keep everyone in the loop.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {detailLoading ? (
                <div className="flex items-center gap-2 text-sm text-slate-500">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Loading details…
                </div>
              ) : detailError ? (
                <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700">
                  {detailError}
                </div>
              ) : !detail ? (
                <div className="rounded-md border border-dashed border-slate-200 bg-slate-50 p-6 text-center text-sm text-slate-500">
                  Select a feedback item to see more details.
                </div>
              ) : (
                <div className="space-y-6">
                  <div className="space-y-2">
                    <div className="flex flex-wrap items-center gap-3">
                      <Badge className={cn("text-[10px] uppercase tracking-wide", STATUS_BADGES[detail.status] || "bg-slate-100 text-slate-700") }>
                        {STATUS_LABELS[detail.status] || detail.status}
                      </Badge>
                      <Badge variant="outline" className="text-[10px] uppercase tracking-wide text-slate-500">
                        {TYPE_LABELS[detail.type] || detail.type}
                      </Badge>
                      <span className="text-xs text-slate-500">Filed {formatRelativeTime(detail.created_at)}</span>
                    </div>
                    <h2 className="text-xl font-semibold text-slate-900">{detail.title}</h2>
                    <p className="text-sm text-slate-600 whitespace-pre-line">{detail.body}</p>
                    <p className="text-xs text-slate-500">
                      Posted by {detail.creator_name || detail.creator_email || "someone"}
                      {detail.creator_email ? ` • ${detail.creator_email}` : ""}
                      {detail.created_at ? ` • ${formatFullDate(detail.created_at)}` : ""}
                    </p>
                  </div>

                  {detail.type === "feature" && (
                    <div className="flex flex-wrap items-center gap-3">
                      <span className="text-sm font-medium text-slate-700">Community votes</span>
                      <div className="flex items-center gap-2">
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          disabled={voteBusy}
                          onClick={() => handleVote(1)}
                          className={cn(
                            detail.user_vote === 1 ? "border-blue-500 bg-blue-50 text-blue-700" : "",
                            "h-9"
                          )}
                        >
                          <ThumbsUp className="w-4 h-4 mr-1" />
                          {detail.upvotes}
                        </Button>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          disabled={voteBusy}
                          onClick={() => handleVote(-1)}
                          className={cn(
                            detail.user_vote === -1 ? "border-red-500 bg-red-50 text-red-700" : "",
                            "h-9"
                          )}
                        >
                          <ThumbsDown className="w-4 h-4 mr-1" />
                          {detail.downvotes}
                        </Button>
                      </div>
                    </div>
                  )}

                  {canUpdateStatus && (
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-medium text-slate-700">Update status:</span>
                      {STATUS_OPTIONS.map((option) => (
                        <Button
                          key={option.value}
                          type="button"
                          variant={detail.status === option.value ? "default" : "outline"}
                          size="sm"
                          disabled={statusUpdating}
                          onClick={() => handleStatusChange(option.value)}
                        >
                          {option.label}
                        </Button>
                      ))}
                    </div>
                  )}

                  <div className="space-y-4">
                    <h3 className="text-sm font-semibold text-slate-700">
                      Discussion ({detail.comments?.length || 0})
                    </h3>
                    {detail.comments && detail.comments.length > 0 ? (
                      <div className="space-y-3">
                        {detail.comments.map((comment) => (
                          <div key={comment.id} className="rounded-md border border-slate-200 bg-white p-3">
                            <div className="mb-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                              <span className="font-medium text-slate-700">
                                {comment.author_name || comment.author_email || "User"}
                              </span>
                              {comment.author_email && (
                                <span className="text-slate-400">{comment.author_email}</span>
                              )}
                              <span>{formatFullDate(comment.created_at)}</span>
                            </div>
                            <p className="text-sm text-slate-700 whitespace-pre-line">{comment.body}</p>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="rounded-md border border-dashed border-slate-200 bg-slate-50 p-4 text-sm text-slate-500">
                        No comments yet. Be the first to add one.
                      </div>
                    )}

                    <form onSubmit={handleAddComment} className="space-y-3">
                      <Textarea
                        rows={4}
                        placeholder="Add a comment, share an update, or ask a follow-up question."
                        value={commentText}
                        onChange={(event) => setCommentText(event.target.value)}
                      />
                      {commentError && <p className="text-sm text-red-600">{commentError}</p>}
                      <Button type="submit" disabled={commentSubmitting}>
                        {commentSubmitting ? (
                          <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        ) : null}
                        Post comment
                      </Button>
                    </form>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
