import React from "react";
import { Input } from "@/components/ui/input";

export default function PublishCadenceStep({ wizard }) {
  const { freqCount, setFreqCount, freqUnit, setFreqUnit, cadenceError } = wizard;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <span className="text-sm">I want to publish</span>
        <Input
          type="number"
          min={1}
          value={freqCount}
          onChange={(event) => {
            const next = Math.max(1, parseInt(event.target.value || "1", 10) || 1);
            setFreqCount(next);
          }}
          className="w-20"
        />
        <span className="text-sm">time(s) every</span>
        <select
          className="border rounded p-2"
          value={freqUnit}
          onChange={(event) => setFreqUnit(event.target.value)}
        >
          <option value="" disabled>
            select...
          </option>
          <option value="day">day</option>
          <option value="week">week</option>
          <option value="bi-weekly">bi-weekly</option>
          <option value="month">month</option>
          <option value="year">year</option>
        </select>
      </div>
      {cadenceError && <p className="text-sm text-red-600">{cadenceError}</p>}
      <p className="text-xs text-muted-foreground">
        We'll tailor the next step based on this.
      </p>
    </div>
  );
}
