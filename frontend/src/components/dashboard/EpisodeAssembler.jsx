import { Button } from "../ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card"
import { Input } from "../ui/input"
import { Label } from "../ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select"
import { ArrowLeft, Loader2 } from "lucide-react"
import { useState, useEffect } from "react"
import { makeApi, isApiError } from "@/lib/apiClient"
import { uploadMediaDirect } from "@/lib/directUpload"

export default function EpisodeAssembler({ templates, onBack, token }) {
  const [selectedTemplateId, setSelectedTemplateId] = useState('');
  const [mainContentFile, setMainContentFile] = useState(null);
  const [outputFilename, setOutputFilename] = useState('');
  const [statusMessage, setStatusMessage] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState('');
  const [assembledEpisode, setAssembledEpisode] = useState(null);
  const [spreakerShows, setSpreakerShows] = useState([]);
  const [selectedShowId, setSelectedShowId] = useState('');
  const [isPublishing, setIsPublishing] = useState(false);

  useEffect(() => {
    const fetchSpreakerShows = async () => {
      try {
  const api = makeApi(token);
  const data = await api.get('/api/spreaker/shows');
  setSpreakerShows(data.shows || []);
      } catch (err) {
        console.error("Failed to fetch Spreaker shows:", err);
      }
    };

    if (token) {
      fetchSpreakerShows();
    }
  }, [token]);

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      setMainContentFile(file);
      setOutputFilename(file.name.replace(/\.[^/.]+$/, ""));
    }
  };

  const handleAssembly = async (e) => {
    e.preventDefault();
    if (!selectedTemplateId || !mainContentFile || !outputFilename) {
      setError("Please select a template, upload a file, and provide an output filename.");
      return;
    }
    setIsProcessing(true);
    setError('');
    setAssembledEpisode(null);
    setStatusMessage('Step 1/2: Uploading main content audio...');
    try {
      const api = makeApi(token);
      const uploadResult = await uploadMediaDirect({
        category: 'main_content',
        file: mainContentFile,
        friendlyName: mainContentFile.name,
        token,
      });
      const uploadedFilename = uploadResult?.[0]?.filename;
      if (!uploadedFilename) {
        throw new Error('Upload did not return a filename.');
      }
      setStatusMessage(`Step 2/2: Assembling episode... This may take a moment.`);
      const assembleResult = await api.post('/api/episodes/assemble', {
        template_id: selectedTemplateId,
        main_content_filename: uploadedFilename,
        output_filename: outputFilename,
        cleanup_options: { removePauses: true, removeFillers: true },
      });
      setStatusMessage(`Success! Episode assembled.`);
      setAssembledEpisode(assembleResult);
    } catch (err) {
      const msg = isApiError(err) ? (err.detail || err.error || err.message) : String(err);
      setError(msg);
      setStatusMessage('');
    } finally {
      setIsProcessing(false);
    }
  };

  const handlePublish = async () => {
    if (!assembledEpisode || !selectedShowId) {
      setError("No assembled episode or show selected for publishing.");
      return;
    }
    setIsPublishing(true);
    setError('');
    setStatusMessage('Publishing to Spreaker...');
    try {
      const api = makeApi(token);
      const result = await api.post('/api/spreaker/upload', {
        show_id: selectedShowId,
        title: outputFilename,
        filename: assembledEpisode.output_path.split('/').pop(),
        description: "Uploaded via Podcast Plus Plus",
      });
      setStatusMessage(`Successfully published to Spreaker! Details: ${result.details}`);
      setAssembledEpisode(null); // Clear the episode after successful publish
    } catch (err) {
      const msg = isApiError(err) ? (err.detail || err.error || err.message) : String(err);
      setError(msg);
    } finally {
      setIsPublishing(false);
    }
  };

  return (
    <div>
      <Button onClick={onBack} variant="ghost" className="mb-4"><ArrowLeft className="w-4 h-4 mr-2" />Back to Dashboard</Button>
      <Card>
        <CardHeader><CardTitle>Create & Publish Episode</CardTitle></CardHeader>
        <CardContent className="space-y-6">
          {!assembledEpisode ? (
            <form onSubmit={handleAssembly} className="space-y-6">
              <div className="space-y-2"><Label htmlFor="template-select">1. Select a Template</Label><Select onValueChange={setSelectedTemplateId} value={selectedTemplateId}><SelectTrigger id="template-select"><SelectValue placeholder="Choose a template..." /></SelectTrigger><SelectContent>{templates.map(t => <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>)}</SelectContent></Select></div>
              <div className="space-y-2"><Label htmlFor="main-audio-upload">2. Upload Main Content Audio</Label><Input id="main-audio-upload" type="file" onChange={handleFileChange} accept="audio/mp3,audio/wav" disabled={isProcessing} /></div>
              <div className="space-y-2"><Label htmlFor="output-filename">3. Enter Episode Title</Label><Input id="output-filename" type="text" placeholder="e.g., My Awesome Episode 1" value={outputFilename} onChange={e => setOutputFilename(e.target.value)} disabled={isProcessing} /></div>
              <Button type="submit" className="w-full" disabled={isProcessing}>{isProcessing ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Assembling...</> : "Assemble Episode"}</Button>
            </form>
          ) : (
            <div className="space-y-6">
              <div className="p-4 text-center bg-green-100 text-green-800 rounded-md">
                <h3 className="font-bold">Assembly Complete!</h3>
                <p>Final file: <strong>{assembledEpisode.output_path}</strong></p>
              </div>
              <div className="space-y-2"><Label htmlFor="show-select">4. Select Spreaker Show</Label><Select onValueChange={setSelectedShowId} value={selectedShowId}><SelectTrigger id="show-select"><SelectValue placeholder="Choose a show to publish to..." /></SelectTrigger><SelectContent>{spreakerShows.length > 0 ? spreakerShows.map(s => <SelectItem key={s.show_id} value={s.show_id}>{s.title}</SelectItem>) : <SelectItem value="no-shows" disabled>No shows found or loaded.</SelectItem>}</SelectContent></Select></div>
              <Button onClick={handlePublish} className="w-full" disabled={isPublishing || !selectedShowId}>{isPublishing ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Publishing...</> : "Publish to Spreaker"}</Button>
            </div>
          )}
          {statusMessage && <p className="text-sm text-center p-2 rounded-md bg-blue-100 text-blue-800">{statusMessage}</p>}
          {error && <p className="text-sm text-center p-2 rounded-md bg-red-100 text-red-800">{error}</p>}
        </CardContent>
      </Card>
    </div>
  );
};
