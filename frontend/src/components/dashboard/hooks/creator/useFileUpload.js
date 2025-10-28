import { useState, useRef, useCallback, useEffect } from 'react';
import { uploadMediaDirect } from '@/lib/directUpload';

/**
 * Manages file upload state for main podcast audio
 * Handles both direct file uploads and pre-uploaded file selection
 * 
 * @param {Object} options
 * @param {string} options.token - Auth token for API calls
 * @param {Function} options.onUploadComplete - Callback when upload finishes
 * @param {Function} options.onPreuploadSelect - Callback when pre-uploaded file selected
 * @param {Function} options.setError - Error message setter from parent
 * @param {Function} options.setStatusMessage - Status message setter from parent
 * @returns {Object} Upload state and handlers
 */
export default function useFileUpload({
  token,
  onUploadComplete,
  onPreuploadSelect,
  setError,
  setStatusMessage,
}) {
  // File state
  const [uploadedFile, setUploadedFile] = useState(null);
  const [uploadedFilename, setUploadedFilename] = useState(null);
  const [selectedPreupload, setSelectedPreupload] = useState(null);
  const [wasRecorded, setWasRecorded] = useState(false);

  // Upload progress tracking
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(null);
  const [uploadStats, setUploadStats] = useState(null); // { loaded, total, bytesPerSecond, etaSeconds }
  const uploadXhrRef = useRef(null);
  
  // Refs for managing upload lifecycle
  const fileInputRef = useRef(null);

  // Transcript state (tied to uploaded file)
  const [transcriptReady, setTranscriptReady] = useState(false);
  const [transcriptPath, setTranscriptPath] = useState(null);
  const transcriptReadyRef = useRef(false);

  // Reset transcript state helper
  const resetTranscriptState = useCallback(() => {
    setTranscriptReady(false);
    setTranscriptPath(null);
    transcriptReadyRef.current = false;
  }, []);

  // Main file upload handler
  const handleFileChange = useCallback(
    async (file) => {
      if (!file) return;

      const MB = 1024 * 1024;
      
      // Validate file type
      if (!(file.type || '').toLowerCase().startsWith('audio/')) {
        setError('Please select an audio file.');
        return;
      }

      // Fetch dynamic size limit from public config
      let maxMb = 500;
      try {
        const res = await fetch('/api/public/config');
        const cfg = await res.json().catch(() => ({}));
        const n = parseInt(String(cfg?.max_upload_mb || '500'), 10);
        if (isFinite(n) && !isNaN(n)) maxMb = Math.min(Math.max(n, 10), 2048);
      } catch {}

      // Validate file size
      if (file.size > maxMb * MB) {
        setError(`Audio exceeds ${maxMb}MB limit.`);
        return;
      }

      // Reset state for new upload
      setUploadedFile(file);
      resetTranscriptState();
      setIsUploading(true);
      setUploadProgress(0);
      setUploadStats(null);
      setStatusMessage('Uploading audio file...');
      setError('');

      try {
        // Upload to GCS via direct upload endpoint
        const entries = await uploadMediaDirect({
          category: 'main_content',
          file,
          friendlyName: file.name,
          token,
          onProgress: ({ percent, loaded, total, bytesPerSecond, etaSeconds }) => {
            if (typeof percent === 'number') setUploadProgress(percent);
            setUploadStats({ loaded, total, bytesPerSecond, etaSeconds });
          },
          onXhrCreate: (xhr) => {
            uploadXhrRef.current = xhr;
          },
        });

        const fname = entries[0]?.filename;
        setUploadedFilename(fname);
        
        // Persist filename to localStorage for recovery
        try {
          if (fname) localStorage.setItem('ppp_uploaded_filename', fname);
        } catch {}

        setStatusMessage('Upload successful!');
        setUploadProgress(100);

        // Notify parent of upload completion
        if (onUploadComplete) {
          onUploadComplete({ filename: fname, file });
        }
      } catch (err) {
        setError(err.message);
        setStatusMessage('');
        setUploadedFile(null);
        
        try {
          localStorage.removeItem('ppp_uploaded_filename');
        } catch {}
        
        setUploadProgress(null);
        setUploadStats(null);
      } finally {
        uploadXhrRef.current = null;
        setIsUploading(false);
        
        // Clear progress UI after animation completes
        setTimeout(() => {
          setUploadProgress(null);
          setUploadStats(null);
        }, 400);
      }
    },
    [token, setError, setStatusMessage, resetTranscriptState, onUploadComplete]
  );

  // Pre-uploaded file selection handler (for media library)
  const handlePreuploadedSelect = useCallback(
    (item) => {
      if (!item) {
        // Deselect - clear all state
        setSelectedPreupload(null);
        setUploadedFilename(null);
        resetTranscriptState();

        // Notify parent of deselection
        if (onPreuploadSelect) {
          onPreuploadSelect(null);
        }
        return;
      }

      const filename = item.filename || null;
      setSelectedPreupload(filename);
      setUploadedFile(null); // Clear direct upload if switching to preuploaded

      if (filename) {
        setUploadedFilename(filename);
        try {
          localStorage.setItem('ppp_uploaded_filename', filename);
        } catch {}
      }

      // Set transcript state from item metadata
      const ready = !!item.transcript_ready;
      setTranscriptReady(ready);
      transcriptReadyRef.current = ready;
      setTranscriptPath(ready ? item.transcript_path || null : null);

      // Notify parent of selection
      if (onPreuploadSelect) {
        onPreuploadSelect(item);
      }
    },
    [resetTranscriptState, onPreuploadSelect]
  );

  // Cancel/abort upload
  const cancelUpload = useCallback(() => {
    // Abort in-flight XHR if active
    try {
      if (uploadXhrRef.current && typeof uploadXhrRef.current.abort === 'function') {
        uploadXhrRef.current.abort();
      }
    } catch {}

    // Clear upload state
    setUploadedFile(null);
    setUploadedFilename(null);
    setUploadProgress(null);
    setUploadStats(null);
    setIsUploading(false);
    resetTranscriptState();

    // Clear localStorage
    try {
      localStorage.removeItem('ppp_uploaded_filename');
      localStorage.removeItem('ppp_uploaded_hint');
      localStorage.removeItem('ppp_transcript_ready');
    } catch {}
  }, [resetTranscriptState]);

  // Audio duration (set externally after analysis)
  const [audioDurationSec, setAudioDurationSec] = useState(null);

  return {
    // File state
    uploadedFile,
    uploadedFilename,
    selectedPreupload,
    wasRecorded,
    
    // Upload progress
    isUploading,
    uploadProgress,
    uploadStats,
    
    // Transcript state
    transcriptReady,
    transcriptPath,
    transcriptReadyRef,
    
    // Audio metadata
    audioDurationSec,
    
    // Refs
    fileInputRef,
    uploadXhrRef,
    
    // Setters (for external control)
    setUploadedFile,
    setUploadedFilename,
    setSelectedPreupload,
    setWasRecorded,
    setTranscriptReady,
    setTranscriptPath,
    setAudioDurationSec,
    setUploadProgress,
    setUploadStats,
    
    // Handlers
    handleFileChange,
    handlePreuploadedSelect,
    cancelUpload,
    resetTranscriptState,
  };
}
