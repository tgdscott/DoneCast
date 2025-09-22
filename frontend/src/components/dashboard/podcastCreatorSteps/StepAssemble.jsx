import React from 'react';
import { Button } from '../../ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../../ui/card';
import { Label } from '../../ui/label';
import { Loader2 } from 'lucide-react';

export default function StepAssemble({
  assemblyComplete,
  processingEstimate,
  publishMode,
  assembledEpisode,
  statusMessage,
  onBack,
}) {
  if (!assemblyComplete) {
    return (
      <div className="space-y-8">
        <CardHeader className="text-center">
          <CardTitle style={{ color: '#2C3E50' }}>Step 6: Assembly In Progress</CardTitle>
        </CardHeader>
        <Card className="border-0 shadow-lg bg-white">
          <CardContent className="p-8 space-y-6 text-center">
            <Loader2 className="w-16 h-16 mx-auto text-blue-600 animate-spin" />
            <p className="text-xl font-semibold text-blue-600 mt-4">We're assembling your episode in the background.</p>
            {processingEstimate ? (
              <p className="text-gray-700 max-w-xl mx-auto">
                Processing time for this episode should be approximately {processingEstimate.low}-{processingEstimate.high} min.
                You can stay here or go back to the dashboard and we'll let you know when it's done.
              </p>
            ) : (
              <p className="text-gray-600 max-w-xl mx-auto">
                You can safely leave this screen. You'll receive a notification when it's ready. This typically takes a few minutes
                depending on length and cleanup.
              </p>
            )}
            <div className="text-sm text-gray-500">If you stay, this page will auto-update when complete.</div>
            <Button onClick={onBack} variant="outline" className="mt-4">
              Back to Dashboard
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <CardHeader className="text-center">
        <CardTitle style={{ color: '#2C3E50' }}>
          Step 6: {publishMode === 'draft' ? 'Draft Ready' : publishMode === 'schedule' ? 'Scheduled' : 'Completed'}
        </CardTitle>
      </CardHeader>
      <Card className="border-0 shadow-lg bg-white">
        <CardContent className="p-6 space-y-6">
          <h3 className="text-2xl font-bold">{assembledEpisode.title}</h3>
          <p className="text-gray-600">{assembledEpisode.description}</p>
          {assembledEpisode.final_audio_url && (
            <div className="mt-4">
              <Label>Listen to the final episode:</Label>
              <audio controls src={assembledEpisode.final_audio_url} className="w-full mt-2">
                Your browser does not support the audio element.
              </audio>
            </div>
          )}
          <div className="p-4 border rounded bg-gray-50 text-sm">
            {publishMode === 'draft' && 'Episode saved as draft.'}
            {publishMode === 'schedule' && 'Episode assembled and scheduled.'}
            {publishMode === 'now' && 'Episode assembled; publish dispatched.'}
          </div>
          {statusMessage && statusMessage.includes('Removed fillers') && (
            <div className="mt-2 text-xs text-gray-500">{statusMessage.split(' | ').slice(1).join(' | ')}</div>
          )}
          {statusMessage && <div className="text-sm text-gray-600">{statusMessage}</div>}
          <div className="flex justify-end pt-4">
            <Button onClick={onBack}>Back to Dashboard</Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
