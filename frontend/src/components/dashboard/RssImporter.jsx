import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ArrowLeft, Loader2, Rss } from "lucide-react";
import { useMemo, useState } from "react";
import { useToast } from "@/hooks/use-toast";
import { makeApi } from '@/lib/apiClient';

export default function RssImporter({ onBack, token }) {
    const [rssUrl, setRssUrl] = useState("");
    const [isLoading, setIsLoading] = useState(false);
    const [autoPublish, setAutoPublish] = useState(false);
    const [publishState, setPublishState] = useState('public');
    const { toast } = useToast();

    const trimmedUrl = rssUrl.trim();

    const handleImport = async () => {
        if (!trimmedUrl) {
            toast({ title: "Error", description: "Please enter an RSS feed URL.", variant: "destructive" });
            return;
        }
        setIsLoading(true);
        try {
            const payload = {
                rss_url: trimmedUrl,
                auto_publish: autoPublish,
                publish_state: autoPublish ? publishState : null,
            };
            const result = await makeApi(token).post('/api/import/rss', payload);
            if (result && result.status && result.status >= 400) throw new Error(result.detail || 'Failed to import from RSS feed.');
            const parts = [
              `Imported "${result.podcast_name}" with ${result.episodes_imported} episodes.`,
              (typeof result.mirrored_count === 'number' ? `${result.mirrored_count} mirrored` : null),
              (typeof result.auto_publish_started === 'number' && autoPublish ? `${result.auto_publish_started} publish jobs started` : null),
            ].filter(Boolean);
            const extra = [];
            if (result?.import_status?.needs_full_import) {
                extra.push('Additional episodes detected — use "Import remaining episodes" on the Manage Podcasts page once you are ready.');
            }
            toast({ title: "Import Successful!", description: [parts.join(' • '), ...extra].filter(Boolean).join(' \n') });
            onBack();
        } catch (err) {
            toast({ title: "Import Failed", description: err.message, variant: "destructive" });
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="p-6">
            <Button onClick={onBack} variant="ghost" className="mb-4">
                <ArrowLeft className="w-4 h-4 mr-2" />
                Back to Dashboard
            </Button>
            <Card className="max-w-xl mx-auto">
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Rss /> Import from RSS Feed
                    </CardTitle>
                    <CardDescription>
                        Paste your public feed URL. We’ll pull the newest five episodes as a preview so you can verify everything looks right before recovering the rest.
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div className="space-y-2">
                        <Label htmlFor="rss-url">RSS Feed URL</Label>
                        <Input
                            id="rss-url"
                            placeholder="https://example.com/podcast.xml"
                            value={rssUrl}
                            onChange={(e) => setRssUrl(e.target.value)}
                        />
                    </div>
                    <div className="rounded-lg border border-border bg-muted/40 p-4 space-y-1 text-sm">
                        <p className="font-medium text-foreground">External feed detected</p>
                        <p className="text-muted-foreground">
                            We will mirror audio locally for seven days so you can review and publish episodes, then automatically clean it up.
                        </p>
                    </div>
                    <div className="space-y-3">
                        <label className="flex items-center gap-2 text-sm">
                            <input type="checkbox" checked={autoPublish} onChange={e=>setAutoPublish(e.target.checked)} />
                            Auto-publish preview episodes
                        </label>
                        <div className="flex items-center gap-2 text-sm">
                            <span>Visibility</span>
                            <select className="h-9 px-2 border rounded" disabled={!autoPublish} value={publishState} onChange={e=>setPublishState(e.target.value)}>
                                <option value="public">Public</option>
                                <option value="unpublished">Private (unpublished)</option>
                                <option value="limited">Limited</option>
                            </select>
                        </div>
                        <p className="text-xs text-muted-foreground">
                            You can recover every episode from the Manage Podcasts screen once you have confirmed the preview looks right.
                        </p>
                    </div>
                    <Button onClick={handleImport} disabled={isLoading} className="w-full">
                        {isLoading ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Importing...</> : "Import Podcast"}
                    </Button>
                </CardContent>
            </Card>
        </div>
    );
}