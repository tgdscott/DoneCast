import React from 'react';
import { Button } from '../../ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../../ui/card';
import { FileAudio, Loader2, Mic, Upload, ArrowLeft, Lightbulb } from 'lucide-react';

// Inline intent questions were removed in favor of the floating modal.

export default function StepUploadAudio({
  uploadedFile,
  uploadedFilename,
  isUploading,
  onFileChange,
  fileInputRef,
  onBack,
  onNext = () => {},
  onEditAutomations,
  onIntentChange,
  onIntentSubmit,
  canProceed = false,
  pendingIntentLabels = [],
  intents = {},
  intentVisibility = {},
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

  const handleIntentSelect = (key, value) => {
    if (typeof onIntentChange === 'function') {
      onIntentChange(key, value);
    }
  };

  const handleContinue = async () => {
    if (typeof onIntentSubmit === 'function') {
      const result = await onIntentSubmit(intents);
      if (result === false) return;
      if (result === true) return;
    }
    onNext();
  };

  return (
    <div className="space-y-8">
      <CardHeader className="text-center">
        <CardTitle style={{ color: '#2C3E50' }}>Step 2: Upload Main Content</CardTitle>
      </CardHeader>
      <Card className="border border-slate-200 bg-slate-50" data-tour-id="episode-upload-guide">
        <CardHeader className="flex flex-col gap-1 pb-2 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle className="text-base flex items-center gap-2 text-slate-800">
            <Lightbulb className="h-4 w-4 text-amber-500" aria-hidden="true" />
            Audio prep checklist
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm text-slate-700">
          <p>
            Give the automation a strong starting point with a clean, final mix. We’ll normalize levels on upload, but the
            clearer the file the better the downstream edit.
          </p>
          <ul className="list-disc space-y-1 pl-5">
            <li>Use WAV or MP3 files under 200&nbsp;MB for the smoothest upload.</li>
            <li>Trim long silences and keep background music subtle—we re-check loudness automatically.</li>
            <li>Re-uploading? Drop the same filename and we’ll detect it so you can skip the wait.</li>
          </ul>
          <details className="rounded-lg border border-dashed border-slate-300 bg-white/80 p-3">
            <summary className="cursor-pointer text-sm font-semibold text-slate-800">How intent questions work</summary>
            <div className="mt-2 space-y-2 text-slate-600">
              <p>
                When we ask about episode intent or offers, those answers steer intro/outro copy, ad reads, and show notes.
                Update them any time before you assemble.
              </p>
              <p>
                Skip for now if you’re unsure—we’ll remind you before publishing and you can fill them in from Automations.
              </p>
            </div>
          </details>
        </CardContent>
      </Card>

      <Card className="border-2 border-dashed border-gray-200 bg-white">
        <CardContent className="p-8">
          <div
            className="border-2 border-dashed rounded-xl p-12 text-center"
            onDragOver={(e) => e.preventDefault()}
            onDrop={handleDrop}
          >
            {(uploadedFile || uploadedFilename) ? (
              <div className="space-y-6">
                <FileAudio className="w-16 h-16 mx-auto text-green-600" />
                <p className="text-xl font-semibold text-green-600">File Ready!</p>
                {uploadedFile && <p className="text-gray-600">{uploadedFile.name}</p>}
                {!uploadedFile && uploadedFilename && (
                  <>
                    <p className="text-gray-600">Server file: {uploadedFilename}</p>
                    <p className="text-xs text-muted-foreground">We found your previously uploaded audio — you can continue without re-uploading.</p>
                  </>
                )}
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

      {(uploadedFile || uploadedFilename) && (
        <Card className="border border-slate-200 bg-slate-50">
          <CardHeader className="pb-2">
            <CardTitle className="text-lg text-slate-900">Before we customize anything…</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {hasPendingIntents ? (
              <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
                We still need your answer about {pendingLabelText}.
              </div>
            ) : (
              <div className="text-sm text-slate-600">
                These answers are saved automatically and you can change them later.
              </div>
            )}
            {typeof onEditAutomations === 'function' && hasPendingIntents && (
              <div className="text-right">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={onEditAutomations}
                  className="text-slate-600 hover:text-slate-900"
                >
                  Answer now
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      <div className="flex flex-col gap-4 pt-8 sm:flex-row sm:items-center sm:justify-between">
        <Button onClick={onBack} variant="outline" size="lg">
          <ArrowLeft className="w-5 h-5 mr-2" />Back to Templates
        </Button>
        {(uploadedFile || uploadedFilename) && (
          <div className="flex w-full flex-col gap-3 sm:w-auto sm:flex-row sm:items-center sm:justify-end">
            <div className="flex justify-end gap-2">
              <Button
                onClick={handleContinue}
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
