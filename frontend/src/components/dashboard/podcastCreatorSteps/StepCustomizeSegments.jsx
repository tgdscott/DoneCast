import React from 'react';
import { Button } from '../../ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../../ui/card';
import { Label } from '../../ui/label';
import { Textarea } from '../../ui/textarea';
import { ArrowLeft, Lightbulb, ListChecks } from 'lucide-react';

export default function StepCustomizeSegments({
  selectedTemplate,
  mediaLibrary,
  uploadedFile,
  ttsValues,
  onTtsChange,
  onBack,
  onNext,
  onOpenVoicePicker,
  voiceNameById,
  voicesLoading,
}) {
  const renderSegmentContent = (segment) => {
    if (segment.segment_type === 'content') {
      return (
        <div className="mt-2 bg-blue-50 p-3 rounded-md">
          <p className="font-semibold text-blue-800">Your Uploaded Audio:</p>
          <p className="text-gray-700">{uploadedFile?.name || 'No file uploaded'}</p>
        </div>
      );
    }

    if (segment.source.source_type === 'tts') {
      const voiceId = segment?.source?.voice_id || '';
      const friendly = voiceNameById[voiceId];
      return (
        <div className="mt-4">
          <div className="mt-2 flex items-center justify-between">
            <span className="text-xs text-gray-500" title={voiceId || undefined}>
              Voice: {friendly || (voiceId || 'default')}{voicesLoading && !friendly ? '…' : ''}
            </span>
            <Button size="sm" variant="outline" onClick={() => onOpenVoicePicker(segment.id)}>
              Change voice
            </Button>
          </div>
          <Label htmlFor={segment.id} className="text-sm font-medium text-gray-700 mb-2 block">
            {segment.source.text_prompt || 'TTS Script'}
          </Label>
          <Textarea
            id={segment.id}
            placeholder="Enter text to be converted to speech..."
            className="min-h-[100px] resize-none text-base bg-white"
            value={ttsValues[segment.id] || ''}
            onChange={(event) => onTtsChange(segment.id, event.target.value)}
          />
        </div>
      );
    }

    if (segment.source.source_type === 'static') {
      const mediaItem = mediaLibrary.find((item) => item.filename.endsWith(segment.source.filename));
      const friendlyName = mediaItem ? mediaItem.friendly_name : segment.source.filename;
      return (
        <p className="text-gray-600 mt-2">
          <span className="font-semibold text-gray-700">Audio File:</span> {friendlyName}
        </p>
      );
    }

    return <p className="text-red-500 mt-2">Unknown segment source type</p>;
  };

  return (
    <div className="space-y-8">
      <CardHeader className="text-center">
        <CardTitle style={{ color: '#2C3E50' }}>Step 3: Customize Your Episode</CardTitle>
        <p className="text-md text-gray-500 pt-2">Review the structure and fill in the required text for any AI-generated segments.</p>
      </CardHeader>
      <Card className="border border-slate-200 bg-slate-50" data-tour-id="episode-segment-guide">
        <CardHeader className="flex flex-col gap-1 pb-2 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle className="text-base flex items-center gap-2 text-slate-800">
            <Lightbulb className="h-4 w-4 text-amber-500" aria-hidden="true" />
            What you’re looking at
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm text-slate-700">
          <p>
            This page shows the pieces we’ll stitch together around your upload. Everything saves as you go—no extra buttons.
          </p>
          <ul className="space-y-2">
            <li className="flex items-start gap-2">
              <ListChecks className="mt-0.5 h-4 w-4 flex-shrink-0 text-primary" aria-hidden="true" />
              <span><strong>Content</strong> is your recording. We wrap intros, outros, and automation around it automatically.</span>
            </li>
            <li className="flex items-start gap-2">
              <ListChecks className="mt-0.5 h-4 w-4 flex-shrink-0 text-primary" aria-hidden="true" />
              <span><strong>AI narration boxes</strong> show the words we’ll speak for you. Edit the text or change the voice if you want a different tone.</span>
            </li>
            <li className="flex items-start gap-2">
              <ListChecks className="mt-0.5 h-4 w-4 flex-shrink-0 text-primary" aria-hidden="true" />
              <span><strong>Library clips</strong> are the intro/outro audio you’ve already saved. We’ll drop them in without extra work.</span>
            </li>
          </ul>
          <p className="text-xs text-slate-500">If everything looks good, you can continue without changing a thing.</p>
        </CardContent>
      </Card>
      <Card className="border-0 shadow-lg bg-white">
        <CardContent className="p-6 space-y-4">
          {selectedTemplate && selectedTemplate.segments ? (
            selectedTemplate.segments.map((segment, index) => (
              <div key={segment.id || index} className="p-4 rounded-md bg-gray-50 border border-gray-200">
                <h4 className="font-semibold text-lg text-gray-800 capitalize">
                  {segment.segment_type.replace('_', ' ')}
                </h4>
                {renderSegmentContent(segment)}
              </div>
            ))
          ) : (
            <div className="text-center py-12">
              <p className="text-lg text-gray-600">This template has no segments to display.</p>
            </div>
          )}
        </CardContent>
      </Card>
      <div className="flex justify-between pt-8">
        <Button onClick={onBack} variant="outline" size="lg">
          <ArrowLeft className="w-5 h-5 mr-2" />Back to Upload
        </Button>
        <Button
          onClick={onNext}
          size="lg"
          className="px-8 py-3 text-lg font-semibold text-white"
          style={{ backgroundColor: '#2C3E50' }}
        >
          Continue to Details
          <ArrowLeft className="w-5 h-5 ml-2 rotate-180" />
        </Button>
      </div>
    </div>
  );
}
