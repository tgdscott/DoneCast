import React from "react";
import { Button } from "@/components/ui/button";

export default function ChoosePathStep({ wizard, stepIndex }) {
  const { path, setPath, setStepIndex } = wizard;

  return (
    <div className="space-y-4">
      <div className="flex gap-3">
        <Button
          variant={path === "new" ? "default" : "outline"}
          onClick={() => {
            setPath("new");
            setStepIndex(stepIndex + 1);
          }}
        >
          Start new
        </Button>
        <Button
          variant={path === "import" ? "default" : "outline"}
          onClick={() => {
            setPath("import");
            setStepIndex(0);
          }}
        >
          Import existing
        </Button>
      </div>
      <p className="text-sm text-muted-foreground">
        Don't worry about breaking anything, and we're going to save as you go.
      </p>
    </div>
  );
}
