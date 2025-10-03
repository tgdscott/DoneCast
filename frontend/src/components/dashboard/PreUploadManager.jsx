import React, { useEffect, useState } from 'react';
import { Button } from '../ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../ui/card';
import { Input } from '../ui/input';
import { Checkbox } from '../ui/checkbox';
import { AlertCircle, AlertTriangle, ArrowLeft, CheckCircle2, Loader2, Upload } from 'lucide-react';
import { makeApi, buildApiUrl } from '@/lib/apiClient';
import { useToast } from '@/hooks/use-toast';
import { convertAudioFileToMp3IfBeneficial } from '@/lib/audioConversion';
import usePublicConfig from '@/hooks/usePublicConfig';

const formatFileSize = (bytes) => {
  if (!Number.isFinite(bytes)) return '';
  const units = ['B', 'KB', 'MB', 'GB'];
  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  const precision = value >= 10 || unitIndex === 0 ? 0 : 1;
  return `${value.toFixed(precision)} ${units[unitIndex]}`;
};

export default function PreUploadManager({
  token,
  onBack,
  onDone,
  defaultEmail = '',
  onUploaded = () => {},
}) {
  const { toast } = useToast();
  const { config: publicConfig, error: publicConfigError } = usePublicConfig();
  const [file, setFile] = useState(null);
  const [friendlyName, setFriendlyName] = useState('');
  const [notify, setNotify] = useState(true);
  const [email, setEmail] = useState(defaultEmail || '');
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(null);
  const [successMessage, setSuccessMessage] = useState('');
  const [error, setError] = useState('');
  const [conversionNotice, setConversionNotice] = useState('');
  const [converting, setConverting] = useState(false);
  const [conversionProgress, setConversionProgress] = useState(null);
  const [submitAfterConvert, setSubmitAfterConvert] = useState(false);
  const [conversionEnabled, setConversionEnabled] = useState(true);

  const CONVERSION_DISABLED_NOTICE =
    'Browser-based audio conversion is disabled. The original file will be uploaded as-is.';

  useEffect(() => {
    if (publicConfig && typeof publicConfig.browser_audio_conversion_enabled === 'boolean') {
      setConversionEnabled(!!publicConfig.browser_audio_conversion_enabled);
    } else if (publicConfigError) {
      setConversionEnabled(true);
    }
  }, [publicConfig, publicConfigError]);

  useEffect(() => {
    if (!conversionEnabled && converting) {
      setConverting(false);
      setConversionProgress(null);
    }
    if (conversionEnabled && conversionNotice === CONVERSION_DISABLED_NOTICE) {
      setConversionNotice('');
    }
  }, [conversionEnabled, converting, conversionNotice]);

  const handleFileChange = async (event) => {
    const selected = event.target.files?.[0];
    if (event.target?.value) {
      // Allow selecting the same file again in the future
      event.target.value = '';
    }
    if (!selected) return;
    setFriendlyName('');
    setSuccessMessage('');
    setError('');
    setConversionNotice('');
    setConversionProgress(null);
    let preparedFile = null;
    if (!conversionEnabled) {
      setFile(selected);
      setConversionNotice(CONVERSION_DISABLED_NOTICE);
      if (submitAfterConvert && selected && friendlyName.trim()) {
        setSubmitAfterConvert(false);
        try {
          await doUpload(selected);
        } catch (uploadError) {
          console.error('Failed to upload after selecting file with conversion disabled', uploadError);
        }
      }
      return;
    }
    setConverting(true);
    setConversionProgress({ phase: 'starting', progress: 0 });
    try {
      const result = await convertAudioFileToMp3IfBeneficial(selected, {
        onProgress: (info = {}) => {
          setConversionProgress((previous) => {
            const next = { ...(previous || {}), ...(info || {}) };
            if (Number.isFinite(info.progress)) {
              next.progress = Math.max(0, Math.min(1, info.progress));
            }
            return next;
          });
        },
      });
      if (result?.converted) {
        setConversionNotice(
          `Converted to MP3 for upload (${formatFileSize(result.originalSize)} → ${formatFileSize(result.convertedSize)}).`,
        );
      } else if (result?.reason === 'already-mp3') {
        setConversionNotice('Selected file is already an MP3 and will be uploaded as-is.');
      } else if (result?.reason === 'not-beneficial' && result?.convertedSize) {
        setConversionNotice(
          `Kept original format because conversion only saved ${formatFileSize(
            Math.max(0, (result.originalSize || 0) - (result.convertedSize || 0)),
          )}.`,
        );
      } else if (result?.reason === 'no-audio-context') {
        setConversionNotice('Browser does not support in-browser conversion; uploading the original file instead.');
      } else if (result?.reason === 'conversion-error' || result?.reason === 'decode-failed') {
        console.error('Audio conversion failed; uploading original file.', result?.error);
        setConversionNotice('Unable to convert automatically. We\'ll upload the original file instead.');
      }
      preparedFile = result?.file || selected;
      setFile(preparedFile);
    } catch (conversionError) {
      console.error('Failed to prepare audio for upload', conversionError);
      setError('We were unable to prepare that audio file. Please try again.');
      setFile(null);
      setSubmitAfterConvert(false);
    } finally {
      setConverting(false);
      setConversionProgress(null);
      // If the user clicked Upload while we were preparing, start upload now
      if (submitAfterConvert && preparedFile && friendlyName.trim()) {
        setSubmitAfterConvert(false);
        try { await doUpload(preparedFile); } catch {}
      }
    }
  };

  // Shared upload logic so we can trigger after conversion
  const doUpload = async (overrideFile) => {
    const trimmedFriendlyName = friendlyName.trim();
    const fileToSend = overrideFile || file;
    if (!fileToSend) {
      setError('Select an audio file to upload.');
      return;
    }
    if (!trimmedFriendlyName) {
      setError('Enter a friendly name for this episode before uploading.');
      return;
    }
    const form = new FormData();
    form.append('files', fileToSend);
    form.append('friendly_names', JSON.stringify([trimmedFriendlyName]));
    form.append('notify_when_ready', notify ? 'true' : 'false');
    if (notify && email) form.append('notify_email', email);

    const startBackgroundUpload = () => new Promise((resolve, reject) => {
      try {
        if (typeof XMLHttpRequest === 'undefined') {
          const api = makeApi(token);
          api.raw('/api/media/upload/main_content', { method: 'POST', body: form }).then(resolve).catch(reject);
          return;
        }
        const xhr = new XMLHttpRequest();
        xhr.open('POST', buildApiUrl('/api/media/upload/main_content'));
        xhr.withCredentials = true;
        if (token) { try { xhr.setRequestHeader('Authorization', `Bearer ${token}`); } catch {} }
        xhr.responseType = 'json';
        xhr.onerror = () => reject(new Error('Upload failed. Please try again.'));
        xhr.onabort = () => reject(new Error('Upload cancelled'));
        xhr.onload = () => {
          const ok = xhr.status >= 200 && xhr.status < 300;
          if (!ok) {
            const payload = xhr.response ?? (() => { try { return JSON.parse(xhr.responseText || ''); } catch { return null; } })();
            const msg = (payload && (payload.error || payload.detail || payload.message)) || `Upload failed with status ${xhr.status}`;
            reject(new Error(msg));
            return;
          }
          resolve(xhr.response);
        };
        xhr.send(form);
      } catch (e) { reject(e); }
    });

    toast({ title: 'Uploading in background', description: 'You can return to your dashboard. We\'ll email you when it\'s processed.' });
    const p = startBackgroundUpload();
    p.then(() => { try { toast({ title: 'Upload received', description: 'Transcription has started.' }); } catch {}
      onUploaded();
    }).catch((err) => { try { toast({ variant: 'destructive', title: 'Upload failed', description: err?.message || 'Unable to upload audio.' }); } catch {} });
    onDone();
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    const trimmedFriendlyName = friendlyName.trim();
    if (!trimmedFriendlyName) {
      setError('Enter a friendly name for this episode before uploading.');
      return;
    }
    if (converting || !file) {
      // Queue submission to run once conversion finishes
      setSubmitAfterConvert(true);
      toast({ title: 'Preparing your audio…', description: 'We\'ll start uploading automatically when the file is ready.' });
      return;
    }
    await doUpload();
  };

  const hasFile = !!file;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 text-sm text-slate-600">
        <Button variant="ghost" onClick={onBack} className="px-0 text-slate-600 hover:text-slate-900">
          <ArrowLeft className="w-4 h-4 mr-1" /> Back
        </Button>
        <span className="text-slate-400">/</span>
        <span>Upload Audio</span>
      </div>

      <Card className="border border-slate-200 shadow-sm">
        <CardHeader>
          <CardTitle className="text-2xl" style={{ color: '#2C3E50' }}>Upload audio for processing</CardTitle>
          <CardDescription className="text-slate-600 text-sm">
            We’ll transcribe everything as soon as it lands. Come back when you get the notification and you can jump straight to assembly.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {(uploading || (typeof uploadProgress === 'number' && uploadProgress < 100)) && (
            <div className="rounded-md border border-slate-200 bg-white p-3 mb-4" aria-live="polite">
              <div className="flex items-center justify-between text-sm">
                <span className="text-slate-700">Uploading audio…</span>
                <span className="text-slate-600">{Math.max(0, Math.min(100, Number(uploadProgress) || 0))}%</span>
              </div>
              <div className="mt-2 h-2 w-full rounded-full bg-slate-200 overflow-hidden">
                <div
                  className="h-full bg-slate-600 transition-all duration-200"
                  style={{ width: `${Math.max(5, Math.min(100, Number(uploadProgress) || 5))}%` }}
                />
              </div>
            </div>
          )}
          <form className="space-y-6" onSubmit={handleSubmit}>
            <div className="border-2 border-dashed border-slate-300 rounded-xl p-8 text-center">
              <input type="file" accept="audio/*" id="preupload-file" className="hidden" onChange={handleFileChange} />
              <label htmlFor="preupload-file" className="inline-flex flex-col items-center gap-3 cursor-pointer">
                <Upload className="w-10 h-10 text-blue-500" />
                <span className="text-sm text-slate-600">
                  {converting
                    ? 'Preparing audio…'
                    : hasFile
                    ? file.name
                    : 'Drag & drop or click to choose an audio file'}
                </span>
              </label>
            </div>

            {converting && (
              <div className="flex flex-col gap-2 text-sm text-slate-600" role="status">
                <div className="flex items-center gap-2">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <div className="flex flex-col">
                    <span>Converting to MP3 for faster upload…</span>
                    {typeof conversionProgress?.progress === 'number' && (
                      <span className="text-xs text-slate-500">
                        {Math.round(conversionProgress.progress * 100)}% complete
                      </span>
                    )}
                  </div>
                </div>
                {typeof conversionProgress?.progress === 'number' && (
                  <div className="mt-1 h-2 w-full rounded-full bg-slate-200 overflow-hidden">
                    <div
                      className="h-full bg-slate-600 transition-all duration-200"
                      style={{ width: `${Math.max(5, Math.min(100, Math.round(conversionProgress.progress * 100) || 0))}%` }}
                    />
                  </div>
                )}
                <div className="mt-2 flex items-start gap-2 rounded-md bg-amber-50 border border-amber-200 p-2 text-amber-800">
                  <AlertTriangle className="w-4 h-4 mt-0.5" />
                  <span>
                    Keep this tab visible while we prepare your audio. Browsers can throttle or pause background or hidden tabs, which may slow or stop conversion.
                  </span>
                </div>
              </div>
            )}

            {conversionNotice && !converting && (
              <div className="flex items-start gap-2 text-sm text-slate-600">
                <CheckCircle2 className="w-4 h-4 mt-0.5 text-emerald-600" />
                <span>{conversionNotice}</span>
              </div>
            )}

            {(hasFile || converting) && (
              <div className="space-y-4">
                <div>
                  <label className="text-sm font-medium text-slate-700">Friendly name</label>
                  <Input
                    value={friendlyName}
                    onChange={(event) => {
                      setFriendlyName(event.target.value);
                      if (error) setError('');
                    }}
                    placeholder="My episode draft"
                    className="mt-1"
                    required
                  />
                </div>

                <div className="flex items-center space-x-2">
                  <Checkbox id="preupload-notify" checked={notify} onCheckedChange={(checked) => setNotify(!!checked)} />
                  <label htmlFor="preupload-notify" className="text-sm text-slate-700">Email me when it’s ready</label>
                </div>
                {notify && (
                  <div>
                    <label className="text-sm font-medium text-slate-700">Notification email</label>
                    <Input
                      type="email"
                      value={email}
                      onChange={(event) => setEmail(event.target.value)}
                      placeholder="you@example.com"
                      className="mt-1"
                    />
                  </div>
                )}
              </div>
            )}

            {error && (
              <div className="flex items-start gap-2 text-sm text-red-600">
                <AlertCircle className="w-4 h-4 mt-0.5" />
                <span>{error}</span>
              </div>
            )}

            {successMessage && (
              <div className="flex items-start gap-2 text-sm text-emerald-600">
                <CheckCircle2 className="w-4 h-4 mt-0.5" />
                <span>{successMessage}</span>
              </div>
            )}

            <div className="flex justify-between">
              <Button type="button" variant="ghost" onClick={onDone}>
                Return to dashboard
              </Button>
              <Button type="submit" disabled={!friendlyName.trim() || (!hasFile && !converting)}>
                {converting ? (
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                ) : (
                  <Upload className="w-4 h-4 mr-2" />
                )}
                {converting ? 'Preparing…' : 'Upload and return'}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
