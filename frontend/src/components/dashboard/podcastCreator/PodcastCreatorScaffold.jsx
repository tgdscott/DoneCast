import React from 'react';
import { Button } from '../../ui/button';
import { Progress } from '../../ui/progress';
import { ArrowLeft, BookText, FileImage, FileUp, Globe, Settings, Wand2, CheckCircle } from 'lucide-react';

const ICON_MAP = {
  BookText,
  FileUp,
  Wand2,
  FileImage,
  Settings,
  Globe,
};

export default function PodcastCreatorScaffold({
  onBack,
  selectedTemplate,
  steps,
  currentStep,
  progressPercentage,
  isUploading,
  uploadProgress,
  usage,
  minutesNearCap,
  minutesRemaining,
  onCancelBuild,
  buildActive,
  children,
}) {
  return (
    <div className="bg-gray-50 min-h-screen">
      <header className="border-b border-gray-200 px-4 py-6 bg-white shadow-sm sticky top-0 z-10">
        <div className="container mx-auto max-w-6xl">
          <div className="flex items-center justify-between">
            <Button variant="ghost" className="text-gray-600" onClick={onBack}>
              <ArrowLeft className="w-4 h-4 mr-2" />
              Back to Dashboard
            </Button>
            <h1 className="text-3xl font-bold" style={{ color: '#2C3E50' }}>
              Episode Creator
            </h1>
            <div className="w-48 text-right space-y-1">
              {selectedTemplate && (
                <div className="text-sm text-gray-500 truncate" title={`Template: ${selectedTemplate.name}`}>
                  Template: {selectedTemplate.name}
                </div>
              )}
              {typeof onCancelBuild === 'function' && currentStep > 1 && currentStep < 6 && buildActive && (
                <Button
                  variant="outline"
                  size="sm"
                  className="text-red-700 border-red-300 hover:bg-red-50"
                  onClick={() => {
                    const ok = window.confirm('Cancel this build and discard in-progress state? You will need to start over.');
                    if (ok) onCancelBuild();
                  }}
                >
                  Cancel Build
                </Button>
              )}
            </div>
          </div>
        </div>
      </header>

      <div className="px-4 py-6 bg-white border-b border-gray-100">
        <div className="container mx-auto max-w-6xl">
          <Progress value={progressPercentage} className="h-2 mb-6" />
          <div className="flex justify-between">
            {steps.map((step) => {
              const IconComponent = ICON_MAP[step.icon] || BookText;
              const isActive = currentStep >= step.number;
              return (
                <div
                  key={step.number}
                  className={`flex flex-col items-center transition-all w-40 text-center ${isActive ? 'text-blue-600' : 'text-gray-600'}`}
                >
                  <div
                    className={`w-12 h-12 rounded-full flex items-center justify-center mb-3 transition-all ${
                      isActive ? 'text-white shadow-lg' : 'bg-gray-100 text-gray-600'
                    }`}
                    style={{ backgroundColor: isActive ? '#2C3E50' : undefined }}
                  >
                    {currentStep > step.number ? (
                      <CheckCircle className="w-6 h-6" />
                    ) : (
                      <IconComponent className="w-6 h-6" />
                    )}
                  </div>
                  <div className="font-semibold text-sm">{step.title}</div>
                </div>
              );
            })}
          </div>
          {(isUploading || (typeof uploadProgress === 'number' && uploadProgress < 100)) && (
            <div className="mt-4">
              <div className="flex items-center justify-between text-sm">
                <span className="text-slate-700">Uploading audio…</span>
                <span className="text-slate-600">{Math.max(0, Math.min(100, Number(uploadProgress) || 0))}%</span>
              </div>
              <div className="h-2 w-full rounded-full bg-slate-200 overflow-hidden">
                <div
                  className="h-full bg-slate-600 transition-all duration-200"
                  style={{ width: `${Math.max(5, Math.min(100, Number(uploadProgress) || 5))}%` }}
                />
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="px-4 py-2 bg-yellow-50 border-b border-yellow-100 text-sm">
        {usage && (
          <div className={`text-center ${minutesNearCap ? 'text-amber-600 font-medium' : ''}`}>
            Processing minutes remaining this month:{' '}
            <span className="font-semibold">
              {usage?.max_processing_minutes_month == null ? '∞' : minutesRemaining ?? '—'}
            </span>
            {usage?.max_processing_minutes_month == null
              ? ' (unlimited during beta)'
              : minutesNearCap
              ? ' (near limit)'
              : ''}
          </div>
        )}
      </div>

      <main className="container mx-auto max-w-6xl px-4 py-8" role="main" aria-label="Episode Creator main content" tabIndex={-1}>
        {children}
      </main>
    </div>
  );
}
