/**
 * Website Controls Component
 * Handles website generation, publishing, and theme generation
 */

import { Loader2, RefreshCcw, ExternalLink, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ServerCog } from "lucide-react";

const statusCopy = {
  draft: { label: "Draft", tone: "bg-amber-100 text-amber-800" },
  published: { label: "Published", tone: "bg-emerald-100 text-emerald-800" },
  updating: { label: "Updating", tone: "bg-sky-100 text-sky-800" },
};

function formatRelativeTime(iso) {
  if (!iso) return "—";
  try {
    const timestamp = new Date(iso).getTime();
    if (Number.isNaN(timestamp)) return "—";
    const diffMs = Date.now() - timestamp;
    if (diffMs < 60_000) return "just now";
    const diffMinutes = Math.floor(diffMs / 60_000);
    if (diffMinutes < 60) return `${diffMinutes}m ago`;
    const diffHours = Math.floor(diffMinutes / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    const diffDays = Math.floor(diffHours / 24);
    if (diffDays < 30) return `${diffDays}d ago`;
    const diffMonths = Math.floor(diffDays / 30);
    if (diffMonths < 12) return `${diffMonths}mo ago`;
    const diffYears = Math.floor(diffMonths / 12);
    return `${diffYears}y ago`;
  } catch (err) {
    console.warn("[website-builder] failed to format timestamp", err);
    return "—";
  }
}

export default function WebsiteControls({
  website,
  loading,
  creating,
  generatingTheme,
  publishing,
  liveUrl,
  onGenerate,
  onGenerateTheme,
  onPublish,
  selectedPodcastId,
}) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-4 shadow-sm space-y-3">
      <div className="flex items-center justify-between">
        <div className="text-xs font-semibold uppercase tracking-widest text-slate-500">Status</div>
        <div>
          {website?.status ? (
            <Badge className={statusCopy[website.status]?.tone || "bg-slate-200 text-slate-700"}>
              {statusCopy[website.status]?.label || website.status}
            </Badge>
          ) : (
            <Badge variant="outline">No site yet</Badge>
          )}
        </div>
      </div>
      <div className="space-y-1 text-xs text-slate-500">
        <div className="flex items-center gap-2">
          <ServerCog className="h-4 w-4 text-slate-400" />
          <span>
            {website?.last_generated_at
              ? `Last generated ${formatRelativeTime(website.last_generated_at)}`
              : "No generation history yet"}
          </span>
        </div>
        {liveUrl && (
          <div className="flex items-center gap-2">
            <ExternalLink className="h-4 w-4 text-slate-400" />
            <a href={liveUrl} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline text-xs break-all">
              {liveUrl}
            </a>
          </div>
        )}
      </div>
      <div className="flex flex-col gap-2">
        <Button onClick={onGenerate} disabled={creating || loading || !selectedPodcastId}>
          {creating ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCcw className="mr-2 h-4 w-4" />}
          {website ? "Refresh with AI" : "Create my site"}
        </Button>
        
        {/* AI Theme Generator button */}
        {website && (
          <Button
            onClick={onGenerateTheme}
            disabled={generatingTheme || loading || !selectedPodcastId}
            variant="outline"
            className="bg-gradient-to-r from-purple-50 to-pink-50 border-purple-200 hover:from-purple-100 hover:to-pink-100"
          >
            {generatingTheme ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Sparkles className="mr-2 h-4 w-4" />
            )}
            Generate AI Theme
          </Button>
        )}
        
        {/* Publish button - only show if website exists */}
        {website && website.subdomain && (
          <Button
            onClick={onPublish}
            disabled={publishing || loading}
            variant={website.status === 'published' ? 'outline' : 'default'}
            className={website.status === 'published' ? '' : 'bg-green-600 hover:bg-green-700'}
          >
            {publishing ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <ExternalLink className="mr-2 h-4 w-4" />
            )}
            {website.status === 'published' ? 'Unpublish' : 'Publish Website'}
          </Button>
        )}
      </div>
    </div>
  );
}


