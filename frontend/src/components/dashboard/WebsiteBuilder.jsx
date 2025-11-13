import { useEffect, useState, useCallback, useRef } from "react";
import { ArrowLeft, Loader2, Layout, Palette, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import VisualEditor from "@/components/website/VisualEditor";
import WebsitePreview from "@/components/website/WebsitePreview";
import WebsiteControls from "@/components/website/WebsiteControls";
import DomainManager from "@/components/website/DomainManager";
import AIChatPanel from "@/components/website/AIChatPanel";
import CSSEditorDialog from "@/components/dashboard/CSSEditorDialog";
import ResetConfirmDialog from "@/components/dashboard/ResetConfirmDialog";
import {
  useWebsiteBuilder,
  useWebsitePublishing,
  useWebsiteDomain,
  useWebsiteChat,
  useWebsiteCSS,
  useWebsiteAITheme,
} from "@/hooks/useWebsiteBuilder";

export default function WebsiteBuilder({ token, podcasts, onBack, allowCustomDomain }) {
  const [selectedPodcastId, setSelectedPodcastId] = useState(() => (podcasts && podcasts[0] ? podcasts[0].id : ""));
  const [builderMode, setBuilderMode] = useState("visual"); // "visual" | "ai"
  const [showCSSEditor, setShowCSSEditor] = useState(false);
  const [showResetDialog, setShowResetDialog] = useState(false);
  const [creating, setCreating] = useState(false);

  // Initialize hooks
  const {
    website,
    loading,
    error,
    setError,
    loadWebsite,
    generateWebsite,
    resetWebsite,
  } = useWebsiteBuilder(token, selectedPodcastId);

  // Create stable callback for website updates using useRef to avoid stale closures
  const loadWebsiteRef = useRef(loadWebsite);
  useEffect(() => {
    loadWebsiteRef.current = loadWebsite;
  }, [loadWebsite]);
  
  const handleWebsiteUpdate = useCallback(async () => {
    await loadWebsiteRef.current();
  }, []); // Stable callback that always uses latest loadWebsite

  const {
    publishing,
    publish,
  } = useWebsitePublishing(token, selectedPodcastId, handleWebsiteUpdate);

  const {
    domainDraft,
    setDomainDraft,
    savingDomain,
    saveDomain,
  } = useWebsiteDomain(token, selectedPodcastId, handleWebsiteUpdate, website?.custom_domain);

  const {
    chatting,
    chatMessage,
    setChatMessage,
    sendChatMessage,
  } = useWebsiteChat(token, selectedPodcastId, handleWebsiteUpdate);

  const {
    cssEditorLoading,
    saveCSS,
    generateAICSS,
  } = useWebsiteCSS(token, selectedPodcastId, handleWebsiteUpdate);

  const {
    generatingTheme,
    generateAITheme,
  } = useWebsiteAITheme(token, selectedPodcastId, handleWebsiteUpdate);


  // Track if we've initialized to prevent loops
  const initializedRef = useRef(false);
  const lastLoadedPodcastIdRef = useRef(null);
  
  // Auto-select first podcast if none selected (only once)
  useEffect(() => {
    if (!initializedRef.current && !selectedPodcastId && podcasts && podcasts.length > 0) {
      initializedRef.current = true;
      setSelectedPodcastId(podcasts[0].id);
    }
  }, [selectedPodcastId]); // Only depend on selectedPodcastId, not podcasts array

  // Load website when podcast changes (only once per podcastId)
  useEffect(() => {
    if (selectedPodcastId && lastLoadedPodcastIdRef.current !== selectedPodcastId) {
      lastLoadedPodcastIdRef.current = selectedPodcastId;
      loadWebsiteRef.current().catch(err => {
        // Error already handled in loadWebsite
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedPodcastId]); // Only depend on selectedPodcastId

  // Handlers
  const handleGenerate = async () => {
    if (!selectedPodcastId) return;
    setCreating(true);
    setError(null);
    try {
      await generateWebsite();
    } catch (err) {
      // Error already handled in hook
    } finally {
      setCreating(false);
    }
  };

  const handlePublish = async () => {
    if (!selectedPodcastId || !website) return;
    const isPublished = website.status === 'published';
    await publish(isPublished);
  };

  const handleChat = async () => {
    if (!chatMessage.trim()) return;
    await sendChatMessage(chatMessage);
  };

  const handleCSSsave = async (css) => {
    await saveCSS(css);
    setShowCSSEditor(false);
  };

  const handleAIGenerateCSS = async (prompt) => {
    await generateAICSS(prompt);
  };

  const handleGenerateAITheme = async () => {
    setError(null);
    try {
      await generateAITheme();
    } catch (err) {
      // Error already handled in hook
    }
  };

  const handleReset = async () => {
    setCreating(true);
    try {
      await resetWebsite();
      setShowResetDialog(false);
    } catch (err) {
      // Error already handled in hook
    } finally {
      setCreating(false);
    }
  };

  const handleDomainSave = async () => {
    setError(null);
    await saveDomain(domainDraft);
  };

  const liveUrl = useMemo(() => {
    if (!website) return null;
    if (website.custom_domain) return `https://${website.custom_domain}`;
    if (website.default_domain) return `https://${website.default_domain}`;
    return null;
  }, [website]);

  const selectedPodcast = useMemo(() => {
    return podcasts.find((p) => p.id === selectedPodcastId);
  }, [podcasts, selectedPodcastId]);

  // If visual mode and podcast selected, show visual editor
  if (builderMode === "visual" && selectedPodcast) {
    return (
      <VisualEditor
        token={token}
        podcast={selectedPodcast}
        onBack={() => setBuilderMode("select")}
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={onBack} className="text-slate-600 hover:text-slate-900">
            <ArrowLeft className="mr-2 h-4 w-4" /> Back to dashboard
          </Button>
          <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Website Builder</div>
        </div>
        
        {/* Mode toggle */}
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant={builderMode === "visual" ? "default" : "outline"}
            onClick={() => setBuilderMode("visual")}
          >
            <Layout className="mr-2 h-4 w-4" />
            Visual Builder
          </Button>
          <Button
            size="sm"
            variant={builderMode === "ai" ? "default" : "outline"}
            onClick={() => setBuilderMode("ai")}
          >
            <RefreshCcw className="mr-2 h-4 w-4" />
            AI Mode (Legacy)
          </Button>
        </div>
      </div>

      <Card className="border border-slate-200 shadow-sm">
        <CardHeader className="space-y-1">
          <CardTitle className="text-2xl font-semibold text-slate-900">AI Website Builder</CardTitle>
          <CardDescription className="text-sm text-slate-600">
            Spin up a shareable site for any of your podcasts, chat with the AI to tweak sections, and publish instantly on a custom subdomain.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {podcasts.length === 0 ? (
            <div className="rounded-md border border-dashed border-slate-300 bg-slate-50 px-4 py-6 text-center text-sm text-slate-600">
              Create a podcast first and it will appear here for website generation.
            </div>
          ) : (
            <div className="grid gap-4 md:grid-cols-[minmax(0,320px)_1fr]">
              <div className="space-y-4">
                <div className="space-y-2">
                  <label className="text-xs font-medium uppercase tracking-wide text-slate-500">Podcast</label>
                  <Select value={selectedPodcastId} onValueChange={setSelectedPodcastId}>
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder="Choose a podcast" />
                    </SelectTrigger>
                    <SelectContent>
                      {podcasts.map((podcast) => (
                        <SelectItem key={podcast.id} value={podcast.id}>
                          {podcast.name || "Untitled podcast"}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <WebsiteControls
                  website={website}
                  loading={loading}
                  creating={creating}
                  generatingTheme={generatingTheme}
                  publishing={publishing}
                  liveUrl={liveUrl}
                  onGenerate={handleGenerate}
                  onGenerateTheme={handleGenerateAITheme}
                  onPublish={handlePublish}
                  selectedPodcastId={selectedPodcastId}
                />

                {allowCustomDomain && (
                  <DomainManager
                    domainDraft={domainDraft}
                    setDomainDraft={setDomainDraft}
                    savingDomain={savingDomain}
                    onSave={handleDomainSave}
                    website={website}
                  />
                )}

                <AIChatPanel
                  chatMessage={chatMessage}
                  setChatMessage={setChatMessage}
                  chatting={chatting}
                  loading={loading}
                  website={website}
                  onSend={handleChat}
                />

                {/* CSS Editor Button */}
                {website && (
                  <div className="space-y-2">
                    <Button
                      onClick={() => setShowCSSEditor(true)}
                      variant="outline"
                      className="w-full"
                      disabled={loading}
                    >
                      <Palette className="mr-2 h-4 w-4" />
                      Customize CSS
                    </Button>
                  </div>
                )}

                {/* Reset Button */}
                {website && (
                  <div className="space-y-2 pt-4 border-t border-slate-200">
                    <Button
                      onClick={() => setShowResetDialog(true)}
                      variant="outline"
                      className="w-full text-red-600 hover:text-red-700 hover:bg-red-50"
                      disabled={loading || creating}
                    >
                      <RotateCcw className="mr-2 h-4 w-4" />
                      Reset to Default Settings
                    </Button>
                    <p className="text-xs text-slate-500 text-center">
                      Removes all customizations and returns to the initial website
                    </p>
                  </div>
                )}
              </div>

              <div className="min-h-[420px]">
                {loading ? (
                  <div className="flex h-full min-h-[420px] items-center justify-center rounded-lg border border-slate-200 bg-white">
                    <Loader2 className="h-6 w-6 animate-spin text-slate-500" />
                  </div>
                ) : (
                  <WebsitePreview website={website} />
                )}
              </div>
            </div>
          )}

          {error && (
            <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {error}
            </div>
          )}
        </CardContent>
      </Card>

      {/* CSS Editor Dialog */}
      <CSSEditorDialog
        isOpen={showCSSEditor}
        onClose={() => setShowCSSEditor(false)}
        currentCSS={website?.global_css || ""}
        onSave={handleCSSsave}
        onAIGenerate={handleAIGenerateCSS}
        isLoading={cssEditorLoading}
      />

      {/* Reset Confirmation Dialog */}
      <ResetConfirmDialog
        isOpen={showResetDialog}
        onClose={() => setShowResetDialog(false)}
        onConfirm={handleReset}
        isLoading={creating}
      />
    </div>
  );
}

