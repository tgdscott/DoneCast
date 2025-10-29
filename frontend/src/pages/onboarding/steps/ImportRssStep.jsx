import React from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function ImportRssStep({ wizard }) {
  const { rssUrl, setRssUrl } = wizard;

  return (
    <div className="grid gap-4">
      <div className="grid grid-cols-4 items-center gap-4">
        <Label htmlFor="rssUrl" className="text-right">
          RSS URL
        </Label>
        <Input
          id="rssUrl"
          value={rssUrl}
          onChange={(event) => setRssUrl(event.target.value)}
          className="col-span-3"
          placeholder="Enter your RSS feed URL"
        />
      </div>
    </div>
  );
}
