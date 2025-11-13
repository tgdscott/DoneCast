/**
 * Domain Manager Component
 * Handles custom domain configuration
 */

import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export default function DomainManager({
  domainDraft,
  setDomainDraft,
  savingDomain,
  onSave,
  website,
}) {
  return (
    <div className="space-y-2">
      <label className="text-xs font-medium uppercase tracking-wide text-slate-500">Custom domain</label>
      <div className="flex flex-col gap-2">
        <Input
          placeholder="e.g. podcast.example.com"
          value={domainDraft}
          onChange={(event) => setDomainDraft(event.target.value)}
          disabled={savingDomain}
        />
        <div className="flex gap-2">
          <Button
            size="sm"
            onClick={onSave}
            disabled={savingDomain}
          >
            {savingDomain ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            Save domain
          </Button>
          {website?.custom_domain && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => setDomainDraft("")}
              disabled={savingDomain}
            >
              Clear
            </Button>
          )}
        </div>
        <p className="text-xs text-slate-500">
          Use a subdomain you control. We will prompt you for DNS once saved.
        </p>
      </div>
    </div>
  );
}


