import React, { useState } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

export default function ShowDetailsStep({ wizard }) {
  const { formData, handleChange } = wizard;
  const name = (formData.podcastName || "").trim();
  const [nameBlurred, setNameBlurred] = useState(false);

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
    </div>
  );
}
