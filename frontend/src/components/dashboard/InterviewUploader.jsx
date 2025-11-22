import { useState, useEffect, useRef } from 'react';
import { Button } from '../ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
// Slider component not available, using Input instead
import { Loader2, Upload, Zoom, X, Volume2, Clock, CheckCircle2 } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { makeApi } from '@/lib/apiClient';
import { uploadMediaDirect } from '@/lib/directUpload';

export default function InterviewUploader({ token, onComplete, onCancel }) {
  const { toast } = useToast();
  const [tracks, setTracks] = useState([]);
  const [isMerging, setIsMerging] = useState(false);
  const [isDetectingZoom, setIsDetectingZoom] = useState(false);
  const [zoomRecordings, setZoomRecordings] = useState([]);
  const [showZoomDetection, setShowZoomDetection] = useState(false);
  const fileInputRef = useRef(null);

  // Load Zoom recordings on mount
  useEffect(() => {
    loadZoomRecordings();
  }, []);

  const loadZoomRecordings = async () => {
    setIsDetectingZoom(true);
    try {
      const api = makeApi(token);
      const recordings = await api.get('/api/media/zoom-recordings?max_sessions=10');
      setZoomRecordings(recordings || []);
    } catch (err) {
      // Zoom detection is optional - don't show error if it fails
      console.log('Zoom detection not available:', err.message);
    } finally {
      setIsDetectingZoom(false);
    }
  };

  const handleFileSelect = (e) => {
    const files = Array.from(e.target.files || []);
    addTracksFromFiles(files);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const addTracksFromFiles = (files) => {
    const newTracks = files.map((file, index) => ({
      id: `file-${Date.now()}-${index}`,
      file,
      participantName: file.name.replace(/\.[^/.]+$/, '').replace(/[_-]/g, ' '),
      gainDb: 0,
      syncOffsetMs: 0,
      uploaded: false,
      uploadedFilename: null,
    }));
    setTracks([...tracks, ...newTracks]);
  };

  const handleZoomTrackSelect = (recording, selectedTracks) => {
    const newTracks = selectedTracks.map((trackInfo, index) => ({
      id: `zoom-${recording.session_name}-${index}`,
      file: null, // Will be uploaded from path
      participantName: trackInfo.participant_name || `Participant ${index + 1}`,
      gainDb: 0,
      syncOffsetMs: 0,
      uploaded: false,
      uploadedFilename: null,
      zoomPath: trackInfo.path,
      sizeBytes: trackInfo.size_bytes,
    }));
    setTracks([...tracks, ...newTracks]);
    setShowZoomDetection(false);
    toast({
      title: 'Tracks added',
      description: `Added ${selectedTracks.length} track(s) from Zoom recording`,
    });
  };

  const removeTrack = (trackId) => {
    setTracks(tracks.filter((t) => t.id !== trackId));
  };

  const updateTrack = (trackId, updates) => {
    setTracks(
      tracks.map((t) => (t.id === trackId ? { ...t, ...updates } : t))
    );
  };

  const uploadTrack = async (track) => {
    if (track.uploaded && track.uploadedFilename) {
      return track.uploadedFilename;
    }

    if (track.zoomPath) {
      // For Zoom tracks, we need to upload from local path
      // In a real implementation, you'd need to read the file from the path
      // For now, we'll require users to select the file manually
      toast({
        title: 'Manual upload required',
        description: 'Please select the Zoom recording file manually',
        variant: 'destructive',
      });
      return null;
    }

    if (!track.file) {
      return null;
    }

    try {
      const result = await uploadMediaDirect({
        category: 'main_content',
        file: track.file,
        friendlyName: track.participantName,
        token,
      });

      if (result && result[0] && result[0].filename) {
        updateTrack(track.id, {
          uploaded: true,
          uploadedFilename: result[0].filename,
        });
        return result[0].filename;
      }
      return null;
    } catch (err) {
      toast({
        title: 'Upload failed',
        description: err.message || 'Failed to upload track',
        variant: 'destructive',
      });
      return null;
    }
  };

  const handleMerge = async () => {
    if (tracks.length < 2) {
      toast({
        title: 'Not enough tracks',
        description: 'Please add at least 2 tracks to merge',
        variant: 'destructive',
      });
      return;
    }

    setIsMerging(true);
    try {
      // Upload all tracks first
      const uploadedFilenames = [];
      for (const track of tracks) {
        const filename = await uploadTrack(track);
        if (filename) {
          uploadedFilenames.push(filename);
        } else {
          throw new Error(`Failed to upload track: ${track.participantName}`);
        }
      }

      if (uploadedFilenames.length < 2) {
        throw new Error('Not enough tracks uploaded successfully');
      }

      // Merge tracks
      const api = makeApi(token);
      const mergeResult = await api.post('/api/media/merge-interview-tracks', {
        track_paths: uploadedFilenames,
        gains_db: tracks.map((t) => t.gainDb),
        sync_offsets_ms: tracks.map((t) => t.syncOffsetMs),
        friendly_name: `Interview - ${tracks.map((t) => t.participantName).join(' & ')}`,
      });

      toast({
        title: 'Success!',
        description: `Merged ${mergeResult.tracks_merged} tracks successfully`,
      });

      if (onComplete) {
        onComplete(mergeResult.merged_filename);
      }
    } catch (err) {
      toast({
        title: 'Merge failed',
        description: err.message || err.detail || 'Failed to merge tracks',
        variant: 'destructive',
      });
    } finally {
      setIsMerging(false);
    }
  };

  return (
    <div className="space-y-6">
      <CardHeader>
        <CardTitle>Interview Recording Upload</CardTitle>
        <p className="text-sm text-slate-500 mt-2">
          Upload multiple audio tracks (e.g., from Zoom) and merge them into a single podcast-ready file.
        </p>
      </CardHeader>

      {/* Zoom Detection */}
      {zoomRecordings.length > 0 && (
        <Card className="border-blue-200 bg-blue-50">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Zoom className="w-5 h-5 text-blue-600" />
                <span className="font-medium text-blue-900">
                  Found {zoomRecordings.length} Zoom recording(s)
                </span>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowZoomDetection(!showZoomDetection)}
              >
                {showZoomDetection ? 'Hide' : 'Show'}
              </Button>
            </div>
            {showZoomDetection && (
              <div className="mt-4 space-y-2">
                {zoomRecordings.map((recording, idx) => (
                  <div
                    key={idx}
                    className="p-3 bg-white rounded border border-blue-200"
                  >
                    <div className="font-medium text-sm">{recording.session_name}</div>
                    <div className="text-xs text-slate-600 mt-1">
                      {recording.audio_tracks.length} audio track(s)
                    </div>
                    <Button
                      size="sm"
                      variant="outline"
                      className="mt-2"
                      onClick={() =>
                        handleZoomTrackSelect(
                          recording,
                          recording.audio_tracks
                        )
                      }
                    >
                      Add All Tracks
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* File Upload */}
      <Card className="border-2 border-dashed border-gray-300">
        <CardContent className="p-8">
          <div className="text-center">
            <Upload className="w-12 h-12 mx-auto text-gray-400 mb-4" />
            <p className="text-lg font-medium text-gray-700 mb-2">
              Add Interview Tracks
            </p>
            <p className="text-sm text-gray-500 mb-4">
              Upload separate audio files for each participant (e.g., Host, Guest)
            </p>
            <Button
              onClick={() => fileInputRef.current?.click()}
              disabled={isMerging}
            >
              <Upload className="w-4 h-4 mr-2" />
              Choose Audio Files
            </Button>
            <input
              ref={fileInputRef}
              type="file"
              accept="audio/*"
              multiple
              onChange={handleFileSelect}
              className="hidden"
            />
          </div>
        </CardContent>
      </Card>

      {/* Track List */}
      {tracks.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Tracks ({tracks.length})</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {tracks.map((track, index) => (
              <div
                key={track.id}
                className="p-4 border rounded-lg bg-slate-50 space-y-3"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">
                        Track {index + 1}: {track.participantName}
                      </span>
                      {track.uploaded && (
                        <CheckCircle2 className="w-4 h-4 text-green-600" />
                      )}
                    </div>
                    {track.file && (
                      <p className="text-xs text-slate-500 mt-1">
                        {track.file.name} ({(track.file.size / 1024 / 1024).toFixed(2)} MB)
                      </p>
                    )}
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => removeTrack(track.id)}
                    disabled={isMerging}
                  >
                    <X className="w-4 h-4" />
                  </Button>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Participant Name */}
                  <div>
                    <Label className="text-xs">Participant Name</Label>
                    <Input
                      value={track.participantName}
                      onChange={(e) =>
                        updateTrack(track.id, { participantName: e.target.value })
                      }
                      placeholder="Host, Guest, etc."
                      disabled={isMerging}
                      className="mt-1"
                    />
                  </div>

                  {/* Volume/Gain */}
                  <div>
                    <Label className="text-xs flex items-center gap-1">
                      <Volume2 className="w-3 h-3" />
                      Volume (dB): {track.gainDb > 0 ? '+' : ''}
                      {track.gainDb.toFixed(1)}
                    </Label>
                    <Input
                      type="number"
                      value={track.gainDb}
                      onChange={(e) => {
                        const value = parseFloat(e.target.value) || 0;
                        updateTrack(track.id, { gainDb: Math.max(-12, Math.min(12, value)) });
                      }}
                      min={-12}
                      max={12}
                      step={0.5}
                      disabled={isMerging}
                      className="mt-1"
                    />
                  </div>

                  {/* Sync Offset */}
                  <div>
                    <Label className="text-xs flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      Sync Offset (ms): {track.syncOffsetMs > 0 ? '+' : ''}
                      {track.syncOffsetMs}
                    </Label>
                    <Input
                      type="number"
                      value={track.syncOffsetMs}
                      onChange={(e) => {
                        const value = parseInt(e.target.value) || 0;
                        updateTrack(track.id, { syncOffsetMs: Math.max(-5000, Math.min(5000, value)) });
                      }}
                      min={-5000}
                      max={5000}
                      step={100}
                      disabled={isMerging}
                      className="mt-1"
                    />
                    <p className="text-xs text-slate-500 mt-1">
                      Adjust if tracks are out of sync (±5000ms range)
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Actions */}
      <div className="flex justify-between gap-4">
        <Button variant="outline" onClick={onCancel} disabled={isMerging}>
          Cancel
        </Button>
        <Button
          onClick={handleMerge}
          disabled={tracks.length < 2 || isMerging}
          className="min-w-[120px]"
        >
          {isMerging ? (
            <>
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              Merging...
            </>
          ) : (
            <>
              Merge & Upload
            </>
          )}
        </Button>
      </div>
    </div>
  );
}

