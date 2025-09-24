import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ArrowLeft, Loader2, Rss } from "lucide-react";
import { useState } from "react";
import { useToast } from "@/hooks/use-toast";
import { makeApi } from '@/lib/apiClient';

export default function RssImporter({ onBack, token }) {
    const [rssUrl, setRssUrl] = useState("");
    const [isLoading, setIsLoading] = useState(false);
    const [downloadAudio, setDownloadAudio] = useState(false);
    const [importTags, setImportTags] = useState(true);
    const [limit, setLimit] = useState(50);
    const [attemptLinkSpreaker, setAttemptLinkSpreaker] = useState(true);
    const [autoPublish, setAutoPublish] = useState(false);
    const [publishState, setPublishState] = useState('public');
    const { toast } = useToast();

    const handleImport = async () => {
        if (!rssUrl) {
            toast({ title: "Error", description: "Please enter an RSS feed URL.", variant: "destructive" });
            return;
        }
        setIsLoading(true);
        try {
            const result = await makeApi(token).post('/api/import/rss', {
                rss_url: rssUrl,
                download_audio: downloadAudio,
                import_tags: importTags,
                limit: (limit ? Number(limit) : null),
                attempt_link_spreaker: attemptLinkSpreaker,
                auto_publish_to_spreaker: autoPublish,
                publish_state: autoPublish ? publishState : null,
            });
            if (result && result.status && result.status >= 400) throw new Error(result.detail || 'Failed to import from RSS feed.');
            const parts = [
              `Imported "${result.podcast_name}" with ${result.episodes_imported} episodes.`,
              (typeof result.mirrored_count === 'number' ? `${result.mirrored_count} mirrored` : null),
              (typeof result.spreaker_linked === 'number' && result.spreaker_attempted ? `${result.spreaker_linked} linked to Spreaker` : null),
              (typeof result.auto_publish_started === 'number' && autoPublish ? `${result.auto_publish_started} publish jobs started` : null),
            ].filter(Boolean);
            toast({ title: "Import Successful!", description: parts.join(' • ') });
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
                        Enter the URL of a public RSS feed to import a podcast and its episodes for testing.
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
                                        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={downloadAudio} onChange={e=>setDownloadAudio(e.target.checked)} />Download audio</label>
                      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={importTags} onChange={e=>setImportTags(e.target.checked)} />Import tags</label>
                      <div className="flex items-center gap-2 text-sm">
                        <span>Limit</span>
                        <Input type="number" min={1} className="h-8 w-24" value={limit} onChange={e=>setLimit(e.target.value)} />
                      </div>
                    </div>
                                        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                                            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={attemptLinkSpreaker} onChange={e=>setAttemptLinkSpreaker(e.target.checked)} />Link to Spreaker if connected</label>
                                            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={autoPublish} onChange={e=>setAutoPublish(e.target.checked)} />Auto-publish to Spreaker</label>
                                            <div className="flex items-center gap-2 text-sm opacity-100">
                                                <span>Visibility</span>
                                                <select className="h-8 px-2 border rounded" disabled={!autoPublish} value={publishState} onChange={e=>setPublishState(e.target.value)}>
                                                    <option value="public">Public</option>
                                                    <option value="unpublished">Private (unpublished)</option>
                                                    <option value="limited">Limited</option>
                                                </select>
                                            </div>
                                        </div>
                    <Button onClick={handleImport} disabled={isLoading} className="w-full">
                        {isLoading ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Importing...</> : "Import Podcast"}
                    </Button>
                </CardContent>
            </Card>
        </div>
    );
}