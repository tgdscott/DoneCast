import React, { useState } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

export default function ShowDetailsStep({ wizard }) {
  const { formData, handleChange } = wizard;
  const name = (formData.podcastName || "").trim();
  const hostBio = (formData.hostBio || "").trim();
  const [nameBlurred, setNameBlurred] = useState(false);

  const bioLen = hostBio.length;
  let bioStatus = { icon: "✗", className: "text-red-600", label: "Too short" };
  if (bioLen >= 50) {
    bioStatus = { icon: "✔", className: "text-green-600", label: "Ready" };
  } else if (bioLen >= 35) {
    bioStatus = { icon: "⚠", className: "text-amber-500", label: "Almost there" };
  }

  return (
    <div className="grid gap-4">
      <div className="grid grid-cols-4 items-center gap-4">
        <Label htmlFor="podcastName" className="text-right">
          Name<span className="text-red-600">*</span>
        </Label>
        <div className="col-span-3">
          <Input
            id="podcastName"
            value={formData.podcastName}
            onChange={handleChange}
            onBlur={() => setNameBlurred(true)}
            placeholder="Enter your podcast name"
          />
          {nameBlurred && name.length > 0 && name.length < 4 && (
            <p className="text-xs text-red-600 mt-1">Name must be at least 4 characters</p>
          )}
        </div>
      </div>
      <div className="grid grid-cols-4 items-center gap-4">
        <Label htmlFor="podcastDescription" className="text-right">
          Description<span className="text-red-600">*</span>
        </Label>
        <Textarea
          id="podcastDescription"
          value={formData.podcastDescription}
          onChange={handleChange}
          className="col-span-3"
          placeholder="Describe your podcast in a few sentences"
        />
      </div>
      <div className="grid grid-cols-4 items-start gap-4">
        <Label htmlFor="hostBio" className="text-right pt-2">
          About the Host<span className="text-red-600">*</span>
        </Label>
        <div className="col-span-3 space-y-2">
          <Textarea
            id="hostBio"
            value={formData.hostBio}
            onChange={handleChange}
            minLength={50}
            placeholder="Tell listeners who you are, why you host this show, and what makes you a great guide (50+ characters)."
          />
          <div className="flex items-center gap-2 text-xs">
            <span className={`${bioStatus.className} font-semibold`}>{bioStatus.icon}</span>
            <span className={hostBio.length < 50 ? "text-red-600" : "text-muted-foreground"}>
              {bioStatus.label} — Required so your website and artwork can feature you properly.
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
