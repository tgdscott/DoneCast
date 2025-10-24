import { useState, useEffect } from "react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Loader2, Sparkles } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export default function CSSEditorDialog({ 
  isOpen, 
  onClose, 
  currentCSS, 
  onSave, 
  onAIGenerate,
  isLoading 
}) {
  const [css, setCSS] = useState(currentCSS || "");
  const [aiPrompt, setAIPrompt] = useState("");
  const [activeTab, setActiveTab] = useState("manual");

  useEffect(() => {
    if (isOpen) {
      setCSS(currentCSS || "");
      setAIPrompt("");
    }
  }, [isOpen, currentCSS]);

  const handleSave = () => {
    onSave(css);
  };

  const handleAIGenerate = async () => {
    if (!aiPrompt.trim()) return;
    await onAIGenerate(aiPrompt);
  };

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle>Customize Website CSS</DialogTitle>
          <DialogDescription>
            Edit the custom CSS for your website or use AI to generate new styles.
          </DialogDescription>
        </DialogHeader>

        <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1 overflow-hidden flex flex-col">
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="manual">Manual Edit</TabsTrigger>
            <TabsTrigger value="ai">
              <Sparkles className="mr-2 h-4 w-4" />
              AI Generate
            </TabsTrigger>
          </TabsList>

          <TabsContent value="manual" className="flex-1 overflow-hidden flex flex-col space-y-4">
            <Textarea
              value={css}
              onChange={(e) => setCSS(e.target.value)}
              placeholder="/* Enter your custom CSS here */"
              className="font-mono text-sm flex-1 min-h-[400px] resize-none"
              disabled={isLoading}
            />
          </TabsContent>

          <TabsContent value="ai" className="flex-1 overflow-hidden flex flex-col space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">
                Describe the style you want
              </label>
              <Textarea
                value={aiPrompt}
                onChange={(e) => setAIPrompt(e.target.value)}
                placeholder="E.g., Make the colors more vibrant and modern, use a dark theme, add animations to buttons..."
                rows={4}
                disabled={isLoading}
              />
              <Button
                onClick={handleAIGenerate}
                disabled={!aiPrompt.trim() || isLoading}
                className="w-full"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Generating CSS...
                  </>
                ) : (
                  <>
                    <Sparkles className="mr-2 h-4 w-4" />
                    Generate CSS with AI
                  </>
                )}
              </Button>
            </div>

            {css && (
              <div className="space-y-2 flex-1 overflow-hidden flex flex-col">
                <label className="text-sm font-medium">Generated CSS (editable)</label>
                <Textarea
                  value={css}
                  onChange={(e) => setCSS(e.target.value)}
                  className="font-mono text-sm flex-1 resize-none"
                  disabled={isLoading}
                />
              </div>
            )}
          </TabsContent>
        </Tabs>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={isLoading}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={isLoading}>
            {isLoading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Saving...
              </>
            ) : (
              "Save CSS"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
