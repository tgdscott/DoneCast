import React from 'react';
import { Button } from '../../ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../../ui/card';

export default function FlubberRetryModal({ open, fuzzyThreshold, onThresholdChange, onRetry, onSkip }) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="text-base">No retakes detected</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="text-sm text-gray-700">You answered “Yes” to Flubber but nothing was found. Try a fuzzier search?</div>
          <div className="text-xs text-gray-600">Fuzzy threshold (0.5–0.95):</div>
          <input
            type="range"
            min={0.5}
            max={0.95}
            step={0.05}
            value={fuzzyThreshold}
            onChange={(event) => onThresholdChange(parseFloat(event.target.value))}
            className="w-full"
          />
          <div className="text-xs">Current: {fuzzyThreshold.toFixed(2)}</div>
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="ghost" onClick={onSkip}>
              Skip
            </Button>
            <Button onClick={onRetry}>Retry</Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
