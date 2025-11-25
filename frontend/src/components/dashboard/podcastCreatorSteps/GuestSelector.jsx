import React, { useState, useEffect, useRef } from 'react';
import { Button } from '../../ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../../ui/card';
import { Label } from '../../ui/label';
import { Input } from '../../ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '../../ui/dialog';
import { useToast } from '@/hooks/use-toast';
import { makeApi, isApiError } from '@/lib/apiClient';
import { Loader2, Mic, Play, Pause, Trash2, Upload, Plus, UserPlus, Check } from 'lucide-react';

export default function GuestSelector({
  token,
  podcastId,
  episodeId, // Optional: if editing an existing episode
  initialGuests = [],
  onGuestsChange,
}) {
  const [libraryGuests, setLibraryGuests] = useState([]);
  const [selectedGuests, setSelectedGuests] = useState([]);
  const [isLoadingLibrary, setIsLoadingLibrary] = useState(true);
  const [isAddingNew, setIsAddingNew] = useState(false);
  const [newGuestName, setNewGuestName] = useState("");
  const [isRecording, setIsRecording] = useState(false);
  const [recordingTime, setRecordingTime] = useState(0);
  const [previewPlaying, setPreviewPlaying] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const audioPlayerRef = useRef(null);
  const timerRef = useRef(null);
  const { toast } = useToast();

  // Load guest library on mount
  useEffect(() => {
    loadLibrary();
  }, [podcastId, token]);

  // Sync initial guests
  useEffect(() => {
    if (initialGuests.length > 0) {
      // Map initial guests to library if possible, or add as temp selected
      setSelectedGuests(initialGuests);
    }
  }, [initialGuests]);

  const loadLibrary = async () => {
    try {
      setIsLoadingLibrary(true);
      const api = makeApi(token);
      const guests = await api.get(`/api/podcasts/${podcastId}/guest-library`);
      setLibraryGuests(guests || []);
    } catch (err) {
      console.error("Failed to load guest library:", err);
    } finally {
      setIsLoadingLibrary(false);
    }
  };

  const handleGuestSelection = (guest) => {
    // Toggle selection
    const isSelected = selectedGuests.some(g => g.id === guest.id);
    let newSelection;
    
    if (isSelected) {
      newSelection = selectedGuests.filter(g => g.id !== guest.id);
    } else {
      newSelection = [...selectedGuests, guest];
    }
    
    setSelectedGuests(newSelection);
    onGuestsChange(newSelection);
  };

  const handleAddNewGuest = async () => {
    if (!newGuestName.trim()) return;
    
    // Create optimistic guest
    const tempId = `temp-${Date.now()}`;
    const newGuest = {
      id: tempId,
      name: newGuestName.trim(),
      gcs_path: null,
      is_new: true
    };
    
    // Add to library (optimistically)
    const updatedLibrary = [...libraryGuests, newGuest];
    setLibraryGuests(updatedLibrary);
    
    // Select immediately
    const newSelection = [...selectedGuests, newGuest];
    setSelectedGuests(newSelection);
    onGuestsChange(newSelection);
    
    // Persist to backend library
    try {
      const api = makeApi(token);
      await api.post(`/api/podcasts/${podcastId}/guest-library`, updatedLibrary.map(g => ({
        id: g.is_new ? undefined : g.id, // Backend generates ID for new
        name: g.name,
        gcs_path: g.gcs_path
      })));
      
      // Reload to get real IDs
      loadLibrary();
      setNewGuestName("");
      setIsAddingNew(false);
      
      toast({ title: "Guest added to library" });
    } catch (err) {
      console.error("Failed to add guest:", err);
      toast({ variant: "destructive", title: "Failed to add guest" });
    }
  };

  const startRecording = async (guest) => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];
      
      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data);
      };
      
      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/wav' });
        await uploadIntro(guest, audioBlob);
        
        stream.getTracks().forEach(track => track.stop());
      };
      
      mediaRecorder.start();
      setIsRecording(guest.id);
      setRecordingTime(0);
      
      timerRef.current = setInterval(() => {
        setRecordingTime(prev => prev + 1);
      }, 1000);
      
      // Auto-stop after 10s
      setTimeout(() => {
        if (mediaRecorderRef.current?.state === 'recording') {
          stopRecording();
        }
      }, 10000);
      
    } catch (err) {
      console.error("Recording error:", err);
      toast({ variant: "destructive", title: "Microphone access denied" });
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current?.state === 'recording') {
      mediaRecorderRef.current.stop();
      setIsRecording(null);
      clearInterval(timerRef.current);
    }
  };

  const uploadIntro = async (guest, audioBlob) => {
    setIsUploading(true);
    try {
      const formData = new FormData();
      formData.append('intro_audio', audioBlob, `${guest.name}_intro.wav`);
      
      const api = makeApi(token);
      // If it's a library guest, use library endpoint
      const endpoint = `/api/podcasts/${podcastId}/guest-library/intro?guest_id=${guest.id}`;
      
      const result = await api.post(endpoint, formData, {
        headers: {
          // Let browser set boundary
        }
      });
      
      // Update local state
      const updatedGuest = { ...guest, gcs_path: result.gcs_uri };
      
      setLibraryGuests(prev => prev.map(g => g.id === guest.id ? updatedGuest : g));
      setSelectedGuests(prev => prev.map(g => g.id === guest.id ? updatedGuest : g));
      
      toast({ title: "Voice intro saved" });
    } catch (err) {
      console.error("Upload failed:", err);
      toast({ variant: "destructive", title: "Upload failed" });
    } finally {
      setIsUploading(false);
    }
  };

  const handlePlayPreview = (guest) => {
    if (previewPlaying === guest.id) {
      audioPlayerRef.current?.pause();
      setPreviewPlaying(null);
    } else {
      if (audioPlayerRef.current) audioPlayerRef.current.pause();
      const audio = new Audio(guest.gcs_path);
      audio.onended = () => setPreviewPlaying(null);
      audio.play();
      audioPlayerRef.current = audio;
      setPreviewPlaying(guest.id);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <Label className="text-base font-medium">Episode Guests</Label>
        <Button 
          variant="outline" 
          size="sm" 
          onClick={() => setIsAddingNew(true)}
          className="h-8"
        >
          <UserPlus className="w-4 h-4 mr-2" />
          Add New Guest
        </Button>
      </div>

      {/* Selected Guests List */}
      {selectedGuests.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-4">
          {selectedGuests.map(guest => (
            <div 
              key={guest.id} 
              className="flex items-center gap-2 bg-slate-100 border border-slate-200 rounded-full px-3 py-1 text-sm"
            >
              <span className="font-medium">{guest.name}</span>
              {guest.gcs_path ? (
                <div className="flex items-center text-green-600 text-xs" title="Voice intro ready">
                  <Mic className="w-3 h-3 mr-1" />
                </div>
              ) : (
                <div className="flex items-center text-amber-500 text-xs" title="Missing voice intro">
                  <Mic className="w-3 h-3 mr-1" />
                </div>
              )}
              <button 
                onClick={() => handleGuestSelection(guest)}
                className="text-slate-400 hover:text-red-500 ml-1"
              >
                <Trash2 className="w-3 h-3" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Guest Library Picker */}
      <Card className="bg-slate-50 border-dashed">
        <CardContent className="p-4">
          {isLoadingLibrary ? (
            <div className="flex justify-center py-4">
              <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
            </div>
          ) : libraryGuests.length === 0 ? (
            <div className="text-center py-6 text-sm text-slate-500">
              No guests in your library yet. Add a guest to reuse them later.
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-[200px] overflow-y-auto pr-2">
              {libraryGuests.map(guest => {
                const isSelected = selectedGuests.some(g => g.id === guest.id);
                return (
                  <div 
                    key={guest.id}
                    className={`
                      flex items-center justify-between p-2 rounded-md border cursor-pointer transition-colors
                      ${isSelected 
                        ? 'bg-blue-50 border-blue-200 ring-1 ring-blue-200' 
                        : 'bg-white border-slate-200 hover:border-blue-300'}
                    `}
                    onClick={() => handleGuestSelection(guest)}
                  >
                    <div className="flex items-center gap-2 overflow-hidden">
                      <div className={`
                        w-4 h-4 rounded-full flex items-center justify-center border
                        ${isSelected ? 'bg-blue-500 border-blue-500' : 'border-slate-300'}
                      `}>
                        {isSelected && <Check className="w-3 h-3 text-white" />}
                      </div>
                      <span className="truncate font-medium text-sm">{guest.name}</span>
                    </div>
                    
                    <div className="flex items-center gap-1" onClick={e => e.stopPropagation()}>
                      {guest.gcs_path ? (
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-6 w-6 rounded-full"
                          onClick={() => handlePlayPreview(guest)}
                          title="Play voice intro"
                        >
                          {previewPlaying === guest.id ? (
                            <Pause className="w-3 h-3" />
                          ) : (
                            <Play className="w-3 h-3 text-slate-600" />
                          )}
                        </Button>
                      ) : (
                        <Button
                          variant="ghost"
                          size="icon"
                          className={`h-6 w-6 rounded-full ${isRecording === guest.id ? 'text-red-500 animate-pulse' : 'text-slate-400'}`}
                          onClick={() => isRecording === guest.id ? stopRecording() : startRecording(guest)}
                          title="Record voice intro (5s)"
                          disabled={isUploading}
                        >
                          <Mic className="w-3 h-3" />
                        </Button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Add New Guest Dialog */}
      <Dialog open={isAddingNew} onOpenChange={setIsAddingNew}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add New Guest</DialogTitle>
            <DialogDescription>
              Add a guest to your library. You can record their voice intro now or later.
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <Label>Guest Name</Label>
            <Input 
              value={newGuestName}
              onChange={e => setNewGuestName(e.target.value)}
              placeholder="e.g. Sarah Smith"
              className="mt-2"
              autoFocus
              onKeyDown={e => e.key === 'Enter' && handleAddNewGuest()}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsAddingNew(false)}>Cancel</Button>
            <Button onClick={handleAddNewGuest} disabled={!newGuestName.trim()}>Add Guest</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

