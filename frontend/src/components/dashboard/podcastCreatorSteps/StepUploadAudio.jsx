import React from 'react';
import { Button } from '../../ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../../ui/card';
import { FileAudio, Loader2, Mic, Upload, ArrowLeft } from 'lucide-react';

export default function StepUploadAudio({
  uploadedFile,
  isUploading,
  onFileChange,
  fileInputRef,
  onBack,
  onNext = () => {},
  onEditAutomations = () => {},
  canProceed = false,
  pendingIntentLabels = [],
}) {
  const handleFileInput = (event) => {
    if (event.target.files?.[0]) {
      onFileChange(event.target.files[0]);
    }
  };

  const handleDrop = (event) => {
    event.preventDefault();
    if (event.dataTransfer.files?.[0]) {
      onFileChange(event.dataTransfer.files[0]);
    }
  };

  const hasPendingIntents = Array.isArray(pendingIntentLabels) && pendingIntentLabels.length > 0;
  const pendingLabelText = hasPendingIntents ? pendingIntentLabels.join(', ') : '';

  return (
    <div className="space-y-8">
      <CardHeader className="text-center">
        <CardTitle style={{ color: '#2C3E50' }}>Step 2: Upload Main Content</CardTitle>
      </CardHeader>
      <Card className="border-2 border-dashed border-gray-200 bg-white">
        <CardContent className="p-8">
          <div className="border-2 border-dashed rounded-xl p-12 text-center" onDragOver={(e) => e.preventDefault()} onDrop={handleDrop}>
            {uploadedFile ? (
              <div className="space-y-6">
                <FileAudio className="w-16 h-16 mx-auto text-green-600" />
                <p className="text-xl font-semibold text-green-600">File Ready!</p>
                <p className="text-gray-600">{uploadedFile.name}</p>
              </div>
            ) : (
              <div className="space-y-6">
                <Mic className="w-16 h-16 mx-auto text-gray-400" />
                <p className="text-2xl font-semibold text-gray-700">Drag your audio file here</p>
                <p className="text-gray-500">or</p>
                <Button
                  onClick={() => fileInputRef.current?.click()}
                  size="lg"
                  className="text-white"
                  style={{ backgroundColor: '#2C3E50' }}
                  disabled={isUploading}
                >
                  {isUploading ? (
                    <>
                      <Loader2 className="w-5 h-5 mr-2 animate-spin" /> Uploading...
                    </>
                  ) : (
                    <>
                      <Upload className="w-5 h-5 mr-2" /> Choose Audio File
                    </>
                  )}
                </Button>
              </div>
            )}
            <input ref={fileInputRef} type="file" accept="audio/*" onChange={handleFileInput} className="hidden" />
          </div>
        </CardContent>
      </Card>
      <div className="flex flex-col gap-4 pt-8 sm:flex-row sm:items-center sm:justify-between">
        <Button onClick={onBack} variant="outline" size="lg">
          <ArrowLeft className="w-5 h-5 mr-2" />Back to Templates
        </Button>
        {uploadedFile && (
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-end w-full sm:w-auto">
            <div className="text-sm text-gray-600 sm:text-right">
              {hasPendingIntents
                ? `We still need your answer about ${pendingLabelText}.`
                : 'Automation answers saved. You can review them before continuing.'}
            </div>
            <div className="flex gap-2 justify-end">
              <Button
                variant="outline"
                onClick={onEditAutomations}
                disabled={isUploading}
              >
                {hasPendingIntents ? 'Answer now' : 'Review answers'}
              </Button>
              <Button
                onClick={onNext}
                size="lg"
                className="text-white"
                style={{ backgroundColor: '#2C3E50' }}
                disabled={!canProceed}
              >
                Continue
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
