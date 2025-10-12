/**
 * Voice Recorder for Onboarding
 * 
 * Simplified version of Recorder.jsx specifically for onboarding wizard.
 * Features:
 * - One-click recording (no device selection)
 * - 60-second maximum duration
 * - Simple preview with play/retry/accept
 * - Auto-upload on accept
 * - Large text support for accessibility
 */

import React, { useState, useRef, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Mic, Square, Play, Pause, RotateCcw, Check, Loader2 } from 'lucide-react';
import { makeApi } from '@/lib/apiClient';
import { useToast } from '@/hooks/use-toast';

export default function VoiceRecorder({ 
  onRecordingComplete, 
  maxDuration = 60,
  type = 'intro', // 'intro' | 'outro'
  largeText = false,
  token 
}) {
  const { toast } = useToast();
  
  // Recording state
  const [isRecording, setIsRecording] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [hasRecording, setHasRecording] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState('');
  
  // Audio state
  const [audioUrl, setAudioUrl] = useState('');
  const [audioBlob, setAudioBlob] = useState(null);
  
  // Refs
  const mediaRecorderRef = useRef(null);
  const streamRef = useRef(null);
  const chunksRef = useRef([]);
  const timerRef = useRef(null);
  const audioRef = useRef(null);
  
  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopStream();
      if (audioUrl) URL.revokeObjectURL(audioUrl);
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [audioUrl]);
  
  const stopStream = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
      streamRef.current = null;
    }
  };
  
  const startRecording = async () => {
    setError('');
    
    // Check browser support
    if (!navigator.mediaDevices || !window.MediaRecorder) {
      setError('Your browser doesn\'t support recording. Try Chrome, Firefox, or Edge.');
      return;
    }
    
    try {
      // Request microphone access
      const stream = await navigator.mediaDevices.getUserMedia({ 
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          sampleRate: 44100
        } 
      });
      
      streamRef.current = stream;
      
      // Determine best mime type
      let mimeType = '';
      if (MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) {
        mimeType = 'audio/webm;codecs=opus';
      } else if (MediaRecorder.isTypeSupported('audio/mp4;codecs=aac')) {
        mimeType = 'audio/mp4;codecs=aac';
      } else if (MediaRecorder.isTypeSupported('audio/webm')) {
        mimeType = 'audio/webm';
      }
      
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      chunksRef.current = [];
      
      recorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) {
          chunksRef.current.push(e.data);
        }
      };
      
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: mimeType || 'audio/webm' });
        const url = URL.createObjectURL(blob);
        setAudioBlob(blob);
        setAudioUrl(url);
        setHasRecording(true);
        stopStream();
      };
      
      mediaRecorderRef.current = recorder;
      recorder.start(100); // Collect data every 100ms
      
      setIsRecording(true);
      setElapsed(0);
      
      // Start timer
      timerRef.current = setInterval(() => {
        setElapsed(prev => {
          const next = prev + 1;
          if (next >= maxDuration) {
            stopRecording();
          }
          return next;
        });
      }, 1000);
      
    } catch (err) {
      console.error('Failed to start recording:', err);
      setError(
        err.name === 'NotAllowedError' 
          ? 'Microphone permission denied. Please allow microphone access and try again.'
          : 'Failed to access microphone. Please check your settings.'
      );
      stopStream();
    }
  };
  
  const stopRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
    }
    
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    
    setIsRecording(false);
    setIsPaused(false);
  };
  
  const togglePlayback = () => {
    if (!audioRef.current) return;
    
    if (isPlaying) {
      audioRef.current.pause();
      setIsPlaying(false);
    } else {
      audioRef.current.play();
      setIsPlaying(true);
    }
  };
  
  const handleRetry = () => {
    // Clean up old recording
    if (audioUrl) {
      URL.revokeObjectURL(audioUrl);
    }
    
    setAudioUrl('');
    setAudioBlob(null);
    setHasRecording(false);
    setElapsed(0);
    setError('');
  };
  
  const handleAccept = async () => {
    if (!audioBlob) return;
    
    setIsUploading(true);
    setError('');
    
    try {
      // Create FormData for upload
      const formData = new FormData();
      const fileName = `${type}_${Date.now()}.${audioBlob.type.includes('mp4') ? 'm4a' : 'webm'}`;
      formData.append('files', audioBlob, fileName);
      
      // Upload to backend
      const response = await makeApi(token).raw(`/api/media/upload/${type}`, {
        method: 'POST',
        body: formData,
      });
      
      if (response && response.length > 0) {
        // Success! Return the media item
        onRecordingComplete(response[0]);
        toast({ 
          title: "Recording saved!", 
          description: `Your ${type} has been uploaded successfully.` 
        });
      } else {
        throw new Error('Upload failed - no response from server');
      }
      
    } catch (err) {
      console.error('Failed to upload recording:', err);
      setError('Failed to save recording. Please try again.');
      toast({ 
        title: "Upload failed", 
        description: "Could not save your recording. Please try again.",
        variant: "destructive"
      });
    } finally {
      setIsUploading(false);
    }
  };
  
  const remainingTime = maxDuration - elapsed;
  
  return (
    <div className="space-y-4 p-6 border rounded-lg bg-gradient-to-br from-purple-50 to-blue-50">
      {!hasRecording ? (
        // Recording Interface
        <div className="text-center space-y-6">
          <div className="space-y-2">
            <h4 className={`font-semibold ${largeText ? 'text-2xl' : 'text-lg'}`}>
              Record Your {type === 'intro' ? 'Intro' : 'Outro'}
            </h4>
            <p className={`text-muted-foreground ${largeText ? 'text-lg' : 'text-sm'}`}>
              Click the button and speak naturally - keep it short and friendly!
            </p>
          </div>
          
          {/* Record Button */}
          <Button
            size={largeText ? "lg" : "default"}
            variant={isRecording ? "destructive" : "default"}
            className={`${largeText ? 'text-xl px-8 py-6' : 'px-6 py-4'} transition-all`}
            onClick={isRecording ? stopRecording : startRecording}
            disabled={isUploading}
          >
            {isRecording ? (
              <>
                <Square className={`${largeText ? 'h-6 w-6' : 'h-5 w-5'} mr-2`} />
                Stop Recording
              </>
            ) : (
              <>
                <Mic className={`${largeText ? 'h-6 w-6' : 'h-5 w-5'} mr-2`} />
                Start Recording
              </>
            )}
          </Button>
          
          {/* Timer & Waveform */}
          {isRecording && (
            <div className="space-y-3">
              <div className={`font-mono font-bold ${largeText ? 'text-3xl' : 'text-2xl'} text-primary`}>
                {Math.floor(elapsed / 60)}:{(elapsed % 60).toString().padStart(2, '0')}
              </div>
              
              <p className={`${largeText ? 'text-lg' : 'text-sm'} text-muted-foreground`}>
                {remainingTime} seconds remaining
              </p>
              
              {/* Simple animated waveform */}
              <div className="flex justify-center items-center gap-1 h-12">
                {[...Array(8)].map((_, i) => (
                  <div
                    key={i}
                    className="w-2 bg-primary rounded-full animate-pulse"
                    style={{
                      height: `${20 + Math.random() * 30}px`,
                      animationDelay: `${i * 0.1}s`,
                      animationDuration: '0.8s'
                    }}
                  />
                ))}
              </div>
            </div>
          )}
          
          {error && (
            <div className="text-destructive text-sm bg-destructive/10 p-3 rounded">
              {error}
            </div>
          )}
        </div>
      ) : (
        // Preview Interface
        <div className="space-y-6">
          <div className="text-center space-y-2">
            <h4 className={`font-semibold ${largeText ? 'text-2xl' : 'text-lg'}`}>
              Listen to Your Recording
            </h4>
            <p className={`text-muted-foreground ${largeText ? 'text-lg' : 'text-sm'}`}>
              Play it back and make sure you're happy with it
            </p>
          </div>
          
          {/* Audio Player */}
          <div className="bg-white p-4 rounded-lg shadow-sm">
            <audio
              ref={audioRef}
              src={audioUrl}
              onEnded={() => setIsPlaying(false)}
              className="hidden"
            />
            
            <div className="flex items-center gap-4">
              <Button
                size={largeText ? "lg" : "default"}
                variant="outline"
                onClick={togglePlayback}
                className="flex-shrink-0"
              >
                {isPlaying ? (
                  <Pause className="h-5 w-5" />
                ) : (
                  <Play className="h-5 w-5" />
                )}
              </Button>
              
              <div className="flex-1">
                <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
                  <div className="h-full bg-primary transition-all" style={{ width: '0%' }} />
                </div>
              </div>
              
              <span className={`${largeText ? 'text-lg' : 'text-sm'} text-muted-foreground font-mono`}>
                {Math.floor(elapsed / 60)}:{(elapsed % 60).toString().padStart(2, '0')}
              </span>
            </div>
          </div>
          
          {/* Action Buttons */}
          <div className="flex gap-3">
            <Button
              size={largeText ? "lg" : "default"}
              variant="outline"
              onClick={handleRetry}
              disabled={isUploading}
              className="flex-1"
            >
              <RotateCcw className="mr-2 h-4 w-4" />
              Try Again
            </Button>
            
            <Button
              size={largeText ? "lg" : "default"}
              onClick={handleAccept}
              disabled={isUploading}
              className="flex-1"
            >
              {isUploading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Saving...
                </>
              ) : (
                <>
                  <Check className="mr-2 h-4 w-4" />
                  Use This Recording
                </>
              )}
            </Button>
          </div>
          
          {error && (
            <div className="text-destructive text-sm bg-destructive/10 p-3 rounded">
              {error}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
