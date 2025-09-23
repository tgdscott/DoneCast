import React from 'react';
import { Button } from '../../ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../../ui/card';
import { FileAudio, Loader2, Mic, Upload, ArrowLeft } from 'lucide-react';

const INTENT_QUESTIONS = [
  {
    key: 'flubber',
    label: 'Should we scan for "flubber" retakes?',
    description:
      'If you recorded any redos or mistakes, we can look for them automatically so you can trim them in the next step.',
  },
  {
    key: 'intern',
    label: 'Do you need the Intern voice segments in this episode?',
    description:
      'Tell us if the AI intern voice should speak in this recording. We only ask when voices are available on your account.',
  },
  {
    key: 'sfx',
    label: 'Are there any words that should trigger sound effects?',
    description:
      'Answer yes if you have cue words that should drop music or SFX during assembly.',
  },
];

const INTENT_VALUES = ['yes', 'no', 'unknown'];

export default function StepUploadAudio({
  uploadedFile,
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
  const visibleIntentQuestions = INTENT_QUESTIONS.filter((q) => intentVisibility?.[q.key] !== false);

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

      {uploadedFile && visibleIntentQuestions.length > 0 && (
        <Card className="border border-slate-200 bg-slate-50">
          <CardHeader className="pb-2">
            <CardTitle className="text-lg text-slate-900">Before we customize anything…</CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            {hasPendingIntents ? (
              <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
                We still need your answer about {pendingLabelText}.
              </div>
            ) : (
              <div className="text-sm text-slate-600">
                These answers are saved automatically and you can change them later from this screen.
              </div>
            )}
            <div className="space-y-5">
              {visibleIntentQuestions.map((question) => {
                const selected = intents?.[question.key] ?? null;
                return (
                  <div
                    key={question.key}
                    className="flex flex-col gap-3 rounded-md border border-slate-200 bg-white p-4 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div className="sm:max-w-md">
                      <div className="text-sm font-medium text-slate-900">{question.label}</div>
                      <div className="mt-1 text-xs leading-relaxed text-slate-600">{question.description}</div>
                    </div>
                    <div className="flex flex-wrap gap-3">
                      {INTENT_VALUES.map((value) => (
                        <label
                          key={value}
                          className="flex cursor-pointer items-center gap-2 rounded-full border border-slate-200 px-3 py-1 text-sm capitalize hover:bg-slate-100"
                        >
                          <input
                            type="radio"
                            name={`intent-${question.key}`}
                            value={value}
                            checked={selected === value}
                            onChange={() => handleIntentSelect(question.key, value)}
                            disabled={isUploading}
                          />
                          {value === 'unknown' ? "I'm not sure" : value}
                        </label>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
            {typeof onEditAutomations === 'function' && (
              <div className="text-right">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={onEditAutomations}
                  className="text-slate-600 hover:text-slate-900"
                >
                  Open detailed view
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
        {uploadedFile && (
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
