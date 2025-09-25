import React, { useEffect, useRef } from 'react';
import { Button } from '../../ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../../ui/card';
import { FileAudio, Loader2, Mic, Upload, ArrowLeft } from 'lucide-react';

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

  // Helper to format a filename by dropping UUID / hash prefixes and extension; prettify.
  const formatDisplayName = (name) => {
    try {
      if (!name) return '';
      let s = name.split(/[\\/]/).pop();
      s = s.replace(/\.[a-z0-9]{2,5}$/i, '');
      s = s.replace(/^(?:[a-f0-9]{8,}|[a-f0-9-]{20,})[_-]+/i, '');
      s = s.replace(/[._-]+/g, ' ').trim();
      if (s.length) s = s[0].toUpperCase() + s.slice(1);
      return s;
    } catch { return name; }
  };

  const autoOpenedRef = useRef(false);
  // Auto-open the intent questionnaire immediately after file upload if pending.
  useEffect(() => {
    if (!autoOpenedRef.current && (uploadedFile || uploadedFilename) && hasPendingIntents && typeof onEditAutomations === 'function') {
      autoOpenedRef.current = true;
      // Slight delay to allow UI to render the success state first.
      setTimeout(() => { try { onEditAutomations(); } catch {} }, 150);
    }
  }, [uploadedFile, uploadedFilename, hasPendingIntents, onEditAutomations]);

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
                {uploadedFile && <p className="text-gray-600">{formatDisplayName(uploadedFile.name)}</p>}
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
                We need your answer about {pendingLabelText}.
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
