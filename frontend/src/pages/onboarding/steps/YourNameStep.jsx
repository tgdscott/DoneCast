import React from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function YourNameStep({ wizard }) {
  const { firstName, setFirstName, lastName, setLastName, nameError, fromManager } = wizard;

  if (fromManager) {
    return <div className="text-sm text-muted-foreground">Skipping…</div>;
  }

  return (
    <div className="grid gap-4">
      <p className="text-sm text-muted-foreground mb-2">
        We'll use your first name to personalize your experience and reminders.
      </p>
      <div className="grid grid-cols-4 items-center gap-4">
        <Label htmlFor="firstName" className="text-right">
          First name<span className="text-red-600">*</span>
        </Label>
        <Input
          id="firstName"
          value={firstName}
          onChange={(event) => setFirstName(event.target.value)}
          className="col-span-3"
          placeholder="e.g., Alex"
        />
      </div>
      <div className="grid grid-cols-4 items-center gap-4">
        <Label htmlFor="lastName" className="text-right">
          Last name
        </Label>
        <Input
          id="lastName"
          value={lastName}
          onChange={(event) => setLastName(event.target.value)}
          className="col-span-3"
          placeholder="(Optional)"
        />
      </div>
      {nameError && <p className="text-sm text-red-600">{nameError}</p>}
    </div>
  );
}
