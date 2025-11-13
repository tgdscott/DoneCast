import React from 'react';
import { Button } from '../ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../ui/card';
import { AlertTriangle, ArrowLeft, Mic, Upload } from 'lucide-react';
import styles from './EpisodeStartOptions.module.css';

export default function EpisodeStartOptions({
  loading = false,
  hasReadyAudio = false,
  errorMessage = '',
  onRetry,
  onBack,
  onChooseRecord,
  onChooseUpload,
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
            Record something new or upload an audio file from your computer.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <button
            type="button"
            onClick={onChooseRecord}
            className={`border border-slate-200 rounded-xl text-left hover:border-blue-400 hover:shadow-sm transition ${styles['uniform-card']}`}
          >
            <Mic className="w-6 h-6 text-blue-500 mb-4" />
            <div className="font-semibold text-slate-800 mb-1">Record Now</div>
            <p className="text-sm text-slate-600">
              Capture your podcast right in the browser using your microphone.
            </p>
          </button>

          <button
            type="button"
            onClick={onChooseUpload}
            className={`border border-slate-200 rounded-xl text-left hover:border-purple-400 hover:shadow-sm transition ${styles['uniform-card']}`}
          >
            <Upload className="w-6 h-6 text-purple-500 mb-4" />
            <div className="font-semibold text-slate-800 mb-1">Upload Audio File</div>
            <p className="text-sm text-slate-600">
              Choose an audio file from your computer to upload and process.
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

    </div>
  );
}
