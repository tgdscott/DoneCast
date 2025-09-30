import React, { useMemo, useState } from 'react';
import { Button } from '../ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../ui/card';
import { Input } from '../ui/input';
import { Checkbox } from '../ui/checkbox';
import { AlertCircle, ArrowLeft, CheckCircle2, Loader2, Upload } from 'lucide-react';
import { makeApi } from '@/lib/apiClient';
import { useToast } from '@/hooks/use-toast';

export default function PreUploadManager({
  token,
  onBack,
  onDone,
  defaultEmail = '',
  onUploaded = () => {},
}) {
  const { toast } = useToast();
  const [file, setFile] = useState(null);
  const [friendlyName, setFriendlyName] = useState('');
  const [notify, setNotify] = useState(true);
  const [email, setEmail] = useState(defaultEmail || '');
  const [uploading, setUploading] = useState(false);
  const [successMessage, setSuccessMessage] = useState('');
  const [error, setError] = useState('');

  const displayName = useMemo(() => {
    if (friendlyName) return friendlyName;
    if (!file) return '';
    try {
      return file.name.replace(/\.[a-z0-9]+$/i, '').replace(/[._-]+/g, ' ').trim();
    } catch {
      return file.name;
    }
  }, [file, friendlyName]);

  const handleFileChange = (event) => {
    const selected = event.target.files?.[0];
    if (!selected) return;
    setFile(selected);
    setFriendlyName('');
    setSuccessMessage('');
    setError('');
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!file) {
      setError('Select an audio file to upload.');
      return;
    }
    setUploading(true);
    setError('');
    setSuccessMessage('');
    try {
      const form = new FormData();
      form.append('files', file);
      if (displayName) {
        form.append('friendly_names', JSON.stringify([displayName]));
      }
      form.append('notify_when_ready', notify ? 'true' : 'false');
      if (notify && email) {
        form.append('notify_email', email);
      }
      const api = makeApi(token);
      await api.raw('/api/media/upload/main_content', { method: 'POST', body: form });
      setSuccessMessage('Upload received! We will notify you once it is processed.');
      setFile(null);
      setFriendlyName('');
      onUploaded();
    } catch (err) {
      setError(err?.message || 'Upload failed.');
      toast({ variant: 'destructive', title: 'Upload failed', description: err?.message || 'Unable to upload audio.' });
    } finally {
      setUploading(false);
    }
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
          <form className="space-y-6" onSubmit={handleSubmit}>
            <div className="border-2 border-dashed border-slate-300 rounded-xl p-8 text-center">
              <input type="file" accept="audio/*" id="preupload-file" className="hidden" onChange={handleFileChange} />
              <label htmlFor="preupload-file" className="inline-flex flex-col items-center gap-3 cursor-pointer">
                <Upload className="w-10 h-10 text-blue-500" />
                <span className="text-sm text-slate-600">
                  {hasFile ? file.name : 'Drag & drop or click to choose an audio file'}
                </span>
              </label>
            </div>

            {hasFile && (
              <div className="space-y-4">
                <div>
                  <label className="text-sm font-medium text-slate-700">Friendly name</label>
                  <Input
                    value={friendlyName}
                    onChange={(event) => setFriendlyName(event.target.value)}
                    placeholder="My episode draft"
                    className="mt-1"
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
              <Button type="submit" disabled={!hasFile || uploading}>
                {uploading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}
                {uploading ? 'Uploading…' : 'Upload audio'}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
