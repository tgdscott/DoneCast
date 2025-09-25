import React from 'react';
import { Button } from '../../ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../../ui/card';
import { Label } from '../../ui/label';
import { Textarea } from '../../ui/textarea';
import { ArrowLeft } from 'lucide-react';

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
            {segment.source.text_prompt || 'AI voice script'}
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

