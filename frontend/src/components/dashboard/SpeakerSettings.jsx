/**
 * Speaker Configuration Component
 * 
 * Manages podcast host speakers and their voice intros for speaker identification.
 * 
 * Features:
 * - Add/remove speakers
 * - Record/upload voice intros (5-second "Hi, my name is X")
 * - Drag-to-reorder speakers (sets speaking order)
 * - Toggle guest support for podcast
 */

import { useState, useEffect, useRef } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { useToast } from "@/hooks/use-toast";
import { makeApi, isApiError } from "@/lib/apiClient";
import * as Icons from "lucide-react";

export default function SpeakerSettings({ podcast, token, isOpen, onClose, onSave }) {
  const [speakers, setSpeakers] = useState([]);
  const [hasGuests, setHasGuests] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [addingSpeaker, setAddingSpeaker] = useState(false);
  const [newSpeakerName, setNewSpeakerName] = useState("");
  const [recordingFor, setRecordingFor] = useState(null); // Speaker being recorded
  const [playingFor, setPlayingFor] = useState(null); // Speaker audio being played
  const { toast } = useToast();

  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const audioPlayerRef = useRef(null);

  // Load speaker configuration
  useEffect(() => {
    if (!isOpen || !podcast) return;

    (async () => {
      setLoading(true);
      try {
        const api = makeApi(token);
        const config = await api.get(`/api/podcasts/${podcast.id}/speakers`);
        
        setSpeakers(config.hosts || []);
        setHasGuests(config.has_guests || false);
      } catch (err) {
        console.error("Failed to load speakers:", err);
        toast({
          variant: "destructive",
          title: "Failed to load speakers",
          description: isApiError(err) ? err.detail || err.error : "Unknown error"
        });
      } finally {
        setLoading(false);
      }
    })();
  }, [isOpen, podcast, token]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const api = makeApi(token);
      
      // Update speaker configuration
      await api.post(`/api/podcasts/${podcast.id}/speakers`, {
        has_guests: hasGuests,
        hosts: speakers.map((s, idx) => ({
          name: s.name,
          gcs_path: s.gcs_path || null,
          order: idx
        }))
      });

      toast({
        title: "Speakers updated",
        description: `${speakers.length} speaker${speakers.length !== 1 ? 's' : ''} configured`
      });

      if (onSave) onSave();
      onClose();
    } catch (err) {
      console.error("Failed to save speakers:", err);
      toast({
        variant: "destructive",
        title: "Failed to save",
        description: isApiError(err) ? err.detail || err.error : "Unknown error"
      });
    } finally {
      setSaving(false);
    }
  };

  const handleAddSpeaker = () => {
    if (!newSpeakerName.trim()) {
      toast({
        variant: "destructive",
        title: "Name required",
        description: "Enter a speaker name"
      });
      return;
    }

    // Check for duplicate
    if (speakers.some(s => s.name.toLowerCase() === newSpeakerName.trim().toLowerCase())) {
      toast({
        variant: "destructive",
        title: "Duplicate name",
        description: "Speaker already exists"
      });
      return;
    }

    setSpeakers(prev => [...prev, {
      name: newSpeakerName.trim(),
      gcs_path: null,
      order: prev.length
    }]);
    
    setNewSpeakerName("");
    setAddingSpeaker(false);

    toast({
      title: "Speaker added",
      description: `${newSpeakerName} added to lineup`
    });
  };

  const handleRemoveSpeaker = (speakerName) => {
    setSpeakers(prev => prev.filter(s => s.name !== speakerName));
    toast({
      title: "Speaker removed",
      description: `${speakerName} removed from lineup`
    });
  };

  const handleMoveUp = (index) => {
    if (index === 0) return;
    const newSpeakers = [...speakers];
    [newSpeakers[index - 1], newSpeakers[index]] = [newSpeakers[index], newSpeakers[index - 1]];
    setSpeakers(newSpeakers);
  };

  const handleMoveDown = (index) => {
    if (index === speakers.length - 1) return;
    const newSpeakers = [...speakers];
    [newSpeakers[index], newSpeakers[index + 1]] = [newSpeakers[index + 1], newSpeakers[index]];
    setSpeakers(newSpeakers);
  };

  const handleStartRecording = async (speakerName) => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      
      audioChunksRef.current = [];
      const mediaRecorder = new MediaRecorder(stream);
      
      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/wav' });
        
        // Upload to backend
        try {
          const formData = new FormData();
          formData.append('intro_audio', audioBlob, `${speakerName}_intro.wav`);
          
          const api = makeApi(token);
          const result = await api.post(
            `/api/podcasts/${podcast.id}/speakers/${encodeURIComponent(speakerName)}/intro`,
            formData,
            {
              headers: {
                // Let browser set Content-Type with boundary for FormData
              }
            }
          );

          // Update speaker with GCS path
          setSpeakers(prev => prev.map(s =>
            s.name === speakerName
              ? { ...s, gcs_path: result.gcs_uri }
              : s
          ));

          toast({
            title: "Voice intro uploaded",
            description: `${speakerName}'s intro saved successfully`
          });
        } catch (err) {
          console.error("Failed to upload intro:", err);
          toast({
            variant: "destructive",
            title: "Upload failed",
            description: isApiError(err) ? err.detail || err.error : "Failed to save voice intro"
          });
        }

        // Stop all tracks
        stream.getTracks().forEach(track => track.stop());
      };

      mediaRecorder.start();
      mediaRecorderRef.current = mediaRecorder;
      setRecordingFor(speakerName);

      // Auto-stop after 10 seconds (recommend 5s intros)
      setTimeout(() => {
        if (mediaRecorderRef.current?.state === 'recording') {
          mediaRecorderRef.current.stop();
          setRecordingFor(null);
        }
      }, 10000);

    } catch (err) {
      console.error("Failed to start recording:", err);
      toast({
        variant: "destructive",
        title: "Recording failed",
        description: "Could not access microphone"
      });
    }
  };

  const handleStopRecording = () => {
    if (mediaRecorderRef.current?.state === 'recording') {
      mediaRecorderRef.current.stop();
      setRecordingFor(null);
    }
  };

  const handlePlayIntro = (speaker) => {
    if (!speaker.gcs_path) return;

    // Simple audio playback (in production, you'd use a signed URL)
    const audio = new Audio(speaker.gcs_path);
    audio.play();
    setPlayingFor(speaker.name);

    audio.onended = () => setPlayingFor(null);
    audio.onerror = () => {
      setPlayingFor(null);
      toast({
        variant: "destructive",
        title: "Playback failed",
        description: "Could not play voice intro"
      });
    };
  };

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Speaker Configuration</DialogTitle>
          <DialogDescription>
            Configure hosts and enable speaker identification in transcripts
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="flex items-center justify-center p-8">
            <Icons.Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="space-y-6">
            {/* Guest Toggle */}
            <div className="flex items-center justify-between p-4 border rounded-lg">
              <div>
                <Label className="text-base font-semibold">Episode Guests</Label>
                <p className="text-sm text-muted-foreground">
                  Enable if your podcast has different guests each episode
                </p>
              </div>
              <Switch
                checked={hasGuests}
                onCheckedChange={setHasGuests}
              />
            </div>

            {/* Speakers List */}
            <div>
              <div className="flex items-center justify-between mb-4">
                <Label className="text-base font-semibold">Hosts</Label>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setAddingSpeaker(true)}
                >
                  <Icons.Plus className="h-4 w-4 mr-2" />
                  Add Host
                </Button>
              </div>

              {speakers.length === 0 ? (
                <Card>
                  <CardContent className="flex flex-col items-center justify-center p-8 text-center">
                    <Icons.Mic className="h-12 w-12 text-muted-foreground mb-4" />
                    <p className="text-sm text-muted-foreground">
                      No speakers configured. Add your podcast hosts to enable speaker identification.
                    </p>
                  </CardContent>
                </Card>
              ) : (
                <div className="space-y-2">
                  {speakers.map((speaker, index) => (
                    <Card key={speaker.name}>
                      <CardContent className="flex items-center gap-4 p-4">
                        {/* Speaker Order */}
                        <div className="flex flex-col gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleMoveUp(index)}
                            disabled={index === 0}
                          >
                            <Icons.ChevronUp className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleMoveDown(index)}
                            disabled={index === speakers.length - 1}
                          >
                            <Icons.ChevronDown className="h-4 w-4" />
                          </Button>
                        </div>

                        {/* Speaker Info */}
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <span className="font-medium">{speaker.name}</span>
                            {speaker.gcs_path && (
                              <Badge variant="success">
                                <Icons.Check className="h-3 w-3 mr-1" />
                                Voice intro recorded
                              </Badge>
                            )}
                          </div>
                          <p className="text-xs text-muted-foreground">
                            Speaking order: {index + 1} (Speaker {String.fromCharCode(65 + index)})
                          </p>
                        </div>

                        {/* Actions */}
                        <div className="flex items-center gap-2">
                          {speaker.gcs_path ? (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => handlePlayIntro(speaker)}
                              disabled={playingFor === speaker.name}
                            >
                              {playingFor === speaker.name ? (
                                <Icons.Loader2 className="h-4 w-4 animate-spin" />
                              ) : (
                                <Icons.Play className="h-4 w-4" />
                              )}
                            </Button>
                          ) : null}

                          <Button
                            variant={recordingFor === speaker.name ? "destructive" : "outline"}
                            size="sm"
                            onClick={() =>
                              recordingFor === speaker.name
                                ? handleStopRecording()
                                : handleStartRecording(speaker.name)
                            }
                          >
                            {recordingFor === speaker.name ? (
                              <>
                                <Icons.Square className="h-4 w-4 mr-2" />
                                Stop
                              </>
                            ) : (
                              <>
                                <Icons.Mic className="h-4 w-4 mr-2" />
                                {speaker.gcs_path ? "Re-record" : "Record"}
                              </>
                            )}
                          </Button>

                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleRemoveSpeaker(speaker.name)}
                          >
                            <Icons.Trash2 className="h-4 w-4 text-destructive" />
                          </Button>
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              )}
            </div>

            {/* Add Speaker Dialog */}
            {addingSpeaker && (
              <Card className="border-2 border-primary">
                <CardContent className="p-4 space-y-4">
                  <div>
                    <Label htmlFor="newSpeakerName">Speaker Name</Label>
                    <Input
                      id="newSpeakerName"
                      placeholder="e.g., Scott"
                      value={newSpeakerName}
                      onChange={(e) => setNewSpeakerName(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") handleAddSpeaker();
                        if (e.key === "Escape") {
                          setAddingSpeaker(false);
                          setNewSpeakerName("");
                        }
                      }}
                      autoFocus
                    />
                  </div>
                  <div className="flex gap-2">
                    <Button onClick={handleAddSpeaker} size="sm">
                      Add Speaker
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        setAddingSpeaker(false);
                        setNewSpeakerName("");
                      }}
                    >
                      Cancel
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Info Box */}
            <Card className="bg-muted/50">
              <CardContent className="p-4">
                <div className="flex gap-3">
                  <Icons.Info className="h-5 w-5 text-blue-500 flex-shrink-0 mt-0.5" />
                  <div className="space-y-2 text-sm">
                    <p className="font-medium">How Speaker Identification Works:</p>
                    <ul className="list-disc list-inside space-y-1 text-muted-foreground">
                      <li>Record a 5-second intro ("Hi, my name is Scott") for each host</li>
                      <li>System prepends intros before transcription</li>
                      <li>AssemblyAI learns voices → Consistent speaker labels</li>
                      <li>Transcripts show "Scott" instead of "Speaker A"</li>
                    </ul>
                    <p className="text-xs text-muted-foreground mt-2">
                      💡 Tip: Order speakers by who typically speaks first
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={saving || loading}>
            {saving ? (
              <>
                <Icons.Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Saving...
              </>
            ) : (
              "Save Changes"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
