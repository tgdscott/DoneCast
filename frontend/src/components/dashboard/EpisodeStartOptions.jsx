import React from 'react';
import { Button } from '../ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../ui/card';
import { AlertTriangle, ArrowLeft, Library, Mic, Upload } from 'lucide-react';

export default function EpisodeStartOptions({
  loading = false,
  hasReadyAudio = false,
  errorMessage = '',
  onRetry,
  onBack,
  onChooseUpload,
  onChooseLibrary,
  onChooseRecord,
}) {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 text-sm text-slate-600">
        <Button variant="ghost" onClick={onBack} className="px-0 text-slate-600 hover:text-slate-900">
          <ArrowLeft className="w-4 h-4 mr-1" /> Dashboard
        </Button>
        <span className="text-slate-400">/</span>
        <span>Start New Episode</span>
      </div>

      <Card className="border border-slate-200 shadow-sm">
        <CardHeader>
          <CardTitle className="text-2xl" style={{ color: '#2C3E50' }}>How do you want to start?</CardTitle>
          <CardDescription className="text-slate-600 text-sm">
            Upload new audio to process in the background, pick from your finished uploads, or record right now.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-3">
          <button
            type="button"
            onClick={onChooseUpload}
            className="border border-slate-200 rounded-xl p-6 text-left hover:border-blue-400 hover:shadow-sm transition"
          >
            <Upload className="w-6 h-6 text-blue-500 mb-4" />
            <div className="font-semibold text-slate-800 mb-1">Upload new audio</div>
            <p className="text-sm text-slate-600">
              Send us your raw mix. We’ll process and transcribe it automatically, then notify you when it’s ready.
            </p>
          </button>

          <div className={`relative ${!hasReadyAudio ? 'group' : ''}`}>
            <button
              type="button"
              onClick={hasReadyAudio ? onChooseLibrary : undefined}
              disabled={!hasReadyAudio || loading}
              title={!hasReadyAudio ? 'You must upload audio first' : undefined}
              className={`border rounded-xl p-6 text-left transition ${
                hasReadyAudio
                  ? 'border-emerald-200 hover:border-emerald-500 hover:shadow-sm'
                  : 'border-slate-200 bg-slate-100 cursor-not-allowed text-slate-400'
              }`}
            >
              <Library className={`w-6 h-6 mb-4 ${hasReadyAudio ? 'text-emerald-500' : 'text-slate-400'}`} />
              <div className="font-semibold text-slate-800 mb-1">Use processed audio</div>
              <p className="text-sm text-slate-600">
                Jump straight into editing with transcripts and automations ready. {hasReadyAudio ? '' : 'Upload audio first and we will unlock this option.'}
              </p>
            </button>

            {!hasReadyAudio && (
              <div className="absolute left-0 -bottom-2 translate-y-full z-10 hidden group-hover:block">
                <div className="max-w-xs rounded-md border border-red-200 bg-white shadow-md p-2">
                  <span className="text-sm text-red-600">You must upload audio first</span>
                </div>
              </div>
            )}
          </div>

          <button
            type="button"
            onClick={onChooseRecord}
            className="border border-slate-200 rounded-xl p-6 text-left hover:border-purple-400 hover:shadow-sm transition"
          >
            <Mic className="w-6 h-6 text-purple-500 mb-4" />
            <div className="font-semibold text-slate-800 mb-1">Record your show</div>
            <p className="text-sm text-slate-600">
              Capture your episode now. Once the recording finishes we’ll process it just like an upload and alert you when it’s ready.
            </p>
          </button>
        </CardContent>
      </Card>

      {errorMessage && (
        <Card className="border border-red-200 bg-red-50">
          <CardContent className="flex items-start justify-between gap-3 text-sm text-red-700">
            <div className="flex items-start gap-3">
              <AlertTriangle className="w-5 h-5 mt-1" />
              <div>{errorMessage}</div>
            </div>
            {onRetry && (
              <button
                type="button"
                onClick={onRetry}
                className="ml-4 shrink-0 inline-flex items-center rounded-md border border-red-300 bg-white px-2 py-1 text-xs font-medium text-red-700 hover:bg-red-50"
              >
                Try again
              </button>
            )}
          </CardContent>
        </Card>
      )}

      {!hasReadyAudio && !errorMessage && (
        <Card className="border border-amber-200 bg-amber-50">
          <CardContent className="flex items-start gap-3 text-sm text-amber-800">
            <AlertTriangle className="w-5 h-5 mt-1" />
            <div>
              We’ll email you as soon as each upload is transcribed so you can come back and assemble without waiting.
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
