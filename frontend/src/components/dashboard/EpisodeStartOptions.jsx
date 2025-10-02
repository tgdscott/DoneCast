import React from 'react';
import { Button } from '../ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../ui/card';
import { AlertTriangle, ArrowLeft, Library, Mic } from 'lucide-react';
import styles from './EpisodeStartOptions.module.css';

export default function EpisodeStartOptions({
  loading = false,
  hasReadyAudio = false,
  errorMessage = '',
  onRetry,
  onBack,
  onChooseRecord,
  onChooseLibrary,
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
            Record something new or jump straight into picking a processed file that’s ready to edit.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <button
            type="button"
            onClick={onChooseRecord}
            className={`border border-slate-200 rounded-xl text-left hover:border-blue-400 hover:shadow-sm transition ${styles['uniform-card']}`}
          >
            <Mic className="w-6 h-6 text-blue-500 mb-4" />
            <div className="font-semibold text-slate-800 mb-1">Record Your Podcast Now</div>
            <p className="text-sm text-slate-600">
              Capture your next episode right in the browser. We’ll save it here so you can edit and publish without leaving CloudPod.
            </p>
          </button>

          <div className="border border-emerald-200 rounded-xl text-left hover:border-emerald-500 hover:shadow-sm transition relative">
            <button
              type="button"
              onClick={onChooseLibrary}
              disabled={loading}
              className={`${styles['uniform-card']} w-full text-left ${loading ? 'opacity-90 cursor-wait' : ''}`}
            >
              <Library className={`w-6 h-6 mb-4 ${hasReadyAudio ? 'text-emerald-500' : 'text-slate-400'}`} />
              <div className="font-semibold text-slate-800 mb-1">Upload and use processed audio</div>
              <p className="text-sm text-slate-600">
                Jump straight into Step 2 to pick a processed upload or add a new file. {hasReadyAudio ? '' : 'If you haven’t uploaded anything yet, we’ll guide you there.'}
              </p>
            </button>

            {!hasReadyAudio && (
              <div className="px-6 pb-4 text-xs text-amber-700 max-w-xs">
                You’ll need at least one processed upload before you can continue, but we’ll show you how to add one.
              </div>
            )}
          </div>
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
          <CardContent className="flex items-center gap-3 text-sm text-amber-800">
            <AlertTriangle className="w-5 h-5" />
            <div>
              We’ll email you as soon as each upload is transcribed so you can come back and assemble without waiting.
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
