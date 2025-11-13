/**
 * AI Chat Panel Component
 * Handles AI chat interactions for website updates
 */

import { Loader2, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

export default function AIChatPanel({
  chatMessage,
  setChatMessage,
  chatting,
  loading,
  website,
  onSend,
}) {
  return (
    <div className="space-y-2">
      <label className="text-xs font-medium uppercase tracking-wide text-slate-500">Ask the builder</label>
      <Textarea
        placeholder="e.g. Add a section for listener testimonials and brighten the hero image."
        value={chatMessage}
        onChange={(event) => setChatMessage(event.target.value)}
        rows={4}
        disabled={chatting || loading || !website}
      />
      <div className="flex justify-end">
        <Button
          onClick={onSend}
          disabled={!chatMessage.trim() || chatting || !website}
        >
          {chatting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Send className="mr-2 h-4 w-4" />}
          Send to AI
        </Button>
      </div>
    </div>
  );
}


