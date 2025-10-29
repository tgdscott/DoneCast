import React from "react";
import { FORMATS } from "@/components/onboarding/OnboardingWizard.jsx";

export default function FormatStep({ wizard }) {
  const { formatKey, setFormatKey } = wizard;

  return (
    <div className="space-y-3">
      <div className="grid gap-3">
        {FORMATS.map((format) => (
          <label
            key={format.key}
            className={`border rounded p-3 cursor-pointer flex gap-3 ${
              formatKey === format.key
                ? "border-blue-600 ring-1 ring-blue-400"
                : "hover:border-gray-400"
            }`}
          >
            <input
              type="radio"
              name="format"
              className="mt-1"
              value={format.key}
              checked={formatKey === format.key}
              onChange={() => setFormatKey(format.key)}
            />
            <span>
              <span className="font-medium">{format.label}</span>
              <br />
              <span className="text-xs text-muted-foreground">{format.desc}</span>
            </span>
          </label>
        ))}
      </div>
    </div>
  );
}
