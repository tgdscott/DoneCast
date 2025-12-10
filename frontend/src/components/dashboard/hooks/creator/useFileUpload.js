import { useState, useRef, useCallback, useEffect, useMemo } from 'react';
import { uploadMediaDirect } from '@/lib/directUpload';
import { makeApi } from '@/lib/apiClient';

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
const DEFAULT_PROCESSING_MODE = 'standard';

const createSegmentRecord = (entry, processingMode = DEFAULT_PROCESSING_MODE) => {
  const makeId = () => {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      try { return crypto.randomUUID(); } catch (_) {}
    }
    return `seg-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  };

  return {
    id: makeId(),
    mediaItemId: entry?.id || null,
    filename: entry?.filename || null,
    friendlyName: entry?.friendly_name || entry?.original_filename || entry?.filename || 'Audio segment',
    processingMode: processingMode === 'advanced' ? 'advanced' : 'standard',
    createdAt: entry?.created_at || null,
  };
};

export default function useFileUpload({
  token,
  onPreuploadSelect,
  setError,
  setStatusMessage,
}) {
  const [uploadedFilename, setUploadedFilename] = useState(null);
  const [selectedPreupload, setSelectedPreupload] = useState(null);
  const [wasRecorded, setWasRecorded] = useState(false);
  const [mainSegments, setMainSegments] = useState([]);
  const [bundleMediaItem, setBundleMediaItem] = useState(null);
  const [bundleSignature, setBundleSignature] = useState(null);
  const [segmentsDirty, setSegmentsDirty] = useState(false);
  const [bundleError, setBundleError] = useState(null);

  const [isBundling, setIsBundling] = useState(false);

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

  const apiClient = useMemo(() => (token ? makeApi(token) : null), [token]);

  // Reset transcript state helper
  const resetTranscriptState = useCallback(() => {
    setTranscriptReady(false);
    setTranscriptPath(null);
    transcriptReadyRef.current = false;
  }, []);

  const cleanupBundle = useCallback(async () => {
    if (!bundleMediaItem?.id || !apiClient) {
      setBundleMediaItem(null);
      return;
    }
    try {
      await apiClient.delete(`/api/media/${bundleMediaItem.id}`);
    } catch (_) {}
    setBundleMediaItem(null);
    setBundleSignature(null);
  }, [bundleMediaItem, apiClient]);

  // Main file upload handler
  const handleFileChange = useCallback(
    async (file, options = {}) => {
      if (!file) return;

      const MB = 1024 * 1024;
      const processingMode = options.processingMode === 'advanced' ? 'advanced' : 'standard';
      
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

      resetTranscriptState();
      setIsUploading(true);
      setUploadProgress(0);
      setUploadStats(null);
      setStatusMessage('Uploading audio file...');
      setError('');

      // Emit upload start event to reduce polling during upload
      try {
        window.dispatchEvent(new CustomEvent('ppp:upload:start'));
      } catch {}

      try {
        const entries = await uploadMediaDirect({
          category: 'main_content',
          file,
          friendlyName: file.name,
          token,
          guest_ids: options.guest_ids || [], // Pass guest IDs if provided
          onProgress: ({ percent, loaded, total, bytesPerSecond, etaSeconds }) => {
            if (typeof percent === 'number') setUploadProgress(percent);
            setUploadStats({ loaded, total, bytesPerSecond, etaSeconds });
          },
          onXhrCreate: (xhr) => {
            uploadXhrRef.current = xhr;
          },
        });

        const entry = entries[0];
        if (!entry) {
          throw new Error('Upload did not return a file reference.');
        }

        setMainSegments(prev => [...prev, createSegmentRecord(entry, processingMode)]);
        setSegmentsDirty(true);
        setSelectedPreupload(null);

        setStatusMessage('Upload successful!');
        setUploadProgress(100);

        try {
          window.dispatchEvent(new CustomEvent('ppp:upload:complete'));
          localStorage.setItem('ppp_last_upload_time', Date.now().toString());
        } catch {}
      } catch (err) {
        setError(err.message);
        setStatusMessage('');
        
        try {
          localStorage.removeItem('ppp_uploaded_filename');
        } catch {}
        
        setUploadProgress(null);
        setUploadStats(null);
      } finally {
        uploadXhrRef.current = null;
        setIsUploading(false);
        
        setTimeout(() => {
          setUploadProgress(null);
          setUploadStats(null);
        }, 400);
      }
    },
    [token, setError, setStatusMessage, resetTranscriptState]
  );

  // Pre-uploaded file selection handler (for media library)
  const handlePreuploadedSelect = useCallback(
    async (item) => {
      if (!item) {
        setSelectedPreupload(null);
        setUploadedFilename(null);
        setMainSegments([]);
        setSegmentsDirty(false);
        setBundleError(null);
        await cleanupBundle();
        resetTranscriptState();
        return;
      }

      await cleanupBundle();
      setMainSegments([]);
      setSegmentsDirty(false);
      setBundleError(null);

      const filename = item.filename || null;
      setSelectedPreupload(filename);

      if (filename) {
        setUploadedFilename(filename);
        try {
          localStorage.setItem('ppp_uploaded_filename', filename);
        } catch {}
      }

      // Verify transcript readiness with a fresh server-side check to avoid stale flags
      const api = apiClient;
      let freshReady = !!item.transcript_ready;
      let freshPath = freshReady ? item.transcript_path || null : null;
      if (api && item.id) {
        try {
          const fresh = await api.get(`/api/media/${item.id}`);
          freshReady = !!fresh?.transcript_ready;
          freshPath = freshReady ? (fresh.transcript_path || null) : null;
        } catch (err) {
          // If the fetch fails, assume transcript is not ready to be safe.
          freshReady = false;
          freshPath = null;
        }
      }

      setTranscriptReady(freshReady);
      transcriptReadyRef.current = freshReady;
      setTranscriptPath(freshPath);

      if (!freshReady) {
        try { setStatusMessage('Transcript not yet available for selected file.'); } catch (_) {}
      }

      if (onPreuploadSelect) {
        onPreuploadSelect(item);
      }
    },
    [cleanupBundle, resetTranscriptState, onPreuploadSelect]
  );

  // Cancel/abort upload
  const cancelUpload = useCallback(() => {
    try {
      if (uploadXhrRef.current && typeof uploadXhrRef.current.abort === 'function') {
        uploadXhrRef.current.abort();
      }
    } catch {}

    setMainSegments([]);
    setSegmentsDirty(false);
    setUploadedFilename(null);
    setUploadProgress(null);
    setUploadStats(null);
    setIsUploading(false);
    setBundleError(null);
    cleanupBundle();
    resetTranscriptState();

    try {
      localStorage.removeItem('ppp_uploaded_filename');
      localStorage.removeItem('ppp_uploaded_hint');
      localStorage.removeItem('ppp_transcript_ready');
    } catch {}
  }, [cleanupBundle, resetTranscriptState]);

  // Audio duration (set externally after analysis)
  const [audioDurationSec, setAudioDurationSec] = useState(null);

  const desiredSignature = useMemo(
    () => JSON.stringify(mainSegments.map(seg => `${seg.mediaItemId}:${seg.processingMode}`)),
    [mainSegments],
  );

  const composeSegments = useCallback(
    async (signatureOverride = null) => {
      if (!apiClient || !mainSegments.length) return null;
      const signature = signatureOverride ?? desiredSignature;

      setIsBundling(true);
      setBundleError(null);

      try {
        await cleanupBundle();

        const payload = {
          segments: mainSegments.map(seg => ({
            media_item_id: seg.mediaItemId,
            filename: seg.filename,
            processing_mode: seg.processingMode,
          })),
        };

        const response = await apiClient.post('/api/media/main-content/bundle', payload);
        const mediaItem = response?.media_item || response;
        if (!mediaItem?.filename) {
          throw new Error('Bundle response missing filename.');
        }

        setBundleMediaItem(mediaItem);
        setUploadedFilename(mediaItem.filename);
        setSegmentsDirty(false);
        setBundleSignature(signature);
        setSelectedPreupload(null);
        resetTranscriptState();

        try {
          localStorage.setItem('ppp_uploaded_filename', mediaItem.filename);
        } catch {}

        return mediaItem;
      } catch (err) {
        setBundleError(err?.message || 'Failed to combine segments.');
        setError(err?.message || 'Failed to combine segments.');
        throw err;
      } finally {
        setIsBundling(false);
      }
    },
    [apiClient, cleanupBundle, desiredSignature, mainSegments, resetTranscriptState, setError],
  );

  useEffect(() => {
    if (mainSegments.length === 0) {
      return;
    }
    if (selectedPreupload) return;
    if (isUploading || isBundling || bundleError) return;
    if (bundleSignature === desiredSignature) return;
    composeSegments(desiredSignature).catch(() => {});
  }, [
    mainSegments.length,
    selectedPreupload,
    isUploading,
    isBundling,
    bundleError,
    bundleSignature,
    desiredSignature,
    composeSegments,
  ]);

  useEffect(() => {
    if (mainSegments.length === 0) {
      cleanupBundle();
      setBundleError(null);
      setSegmentsDirty(false);
      if (bundleMediaItem) {
        setUploadedFilename(null);
        resetTranscriptState();
      }
    }
  }, [mainSegments.length, cleanupBundle, bundleMediaItem, resetTranscriptState]);

  const removeSegment = useCallback((segmentId) => {
    setMainSegments(prev => prev.filter(seg => seg.id !== segmentId));
    setSegmentsDirty(true);
  }, []);

  const updateSegmentProcessingMode = useCallback((segmentId, mode) => {
    setMainSegments(prev => prev.map(seg => (
      seg.id === segmentId ? { ...seg, processingMode: mode === 'advanced' ? 'advanced' : 'standard' } : seg
    )));
    setSegmentsDirty(true);
  }, []);

  const reorderSegments = useCallback((startIndex, endIndex) => {
    setMainSegments(prev => {
      if (startIndex === endIndex || startIndex < 0 || endIndex < 0 || startIndex >= prev.length || endIndex >= prev.length) {
        return prev;
      }
      const next = [...prev];
      const [moved] = next.splice(startIndex, 1);
      next.splice(endIndex, 0, moved);
      return next;
    });
    setSegmentsDirty(true);
  }, []);

  return {
    // File state
    uploadedFilename,
    selectedPreupload,
    wasRecorded,
    mainSegments,
    bundleMediaItem,
    segmentsDirty,
    isBundling,
    bundleError,
    
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
    removeSegment,
    updateSegmentProcessingMode,
    reorderSegments,
    composeSegments,
    cancelUpload,
    resetTranscriptState,
  };
}
