import { useState, useCallback, useRef } from 'react';
import { makeApi, coerceArray } from '@/lib/apiClient';
import { toast } from '@/hooks/use-toast';

export default function useMediaManagement({ token, episodeDetails, setEpisodeDetails }) {
  const [mediaLibrary, setMediaLibrary] = useState([]);
  const [isUploadingCover, setIsUploadingCover] = useState(false);
  const [coverNeedsUpload, setCoverNeedsUpload] = useState(false);
  const coverArtInputRef = useRef(null);
  const coverCropperRef = useRef(null);

  const refreshMediaLibrary = useCallback(async () => {
    try {
      const api = makeApi(token);
      const data = await api.get('/api/media/');
      setMediaLibrary(coerceArray(data));
      return data;
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: err.message });
      return null;
    }
  }, [token]);

  const uploadCover = async (file) => {
    const MB = 1024 * 1024;
    const ct = (file?.type || '').toLowerCase();
    if (!ct.startsWith('image/')) throw new Error('Cover must be an image file.');
    if (file.size > 15 * MB) throw new Error('Cover image exceeds 15MB limit.');

    const fd = new FormData();
    fd.append('files', file);
    fd.append('friendly_names', JSON.stringify([file.name]));

    const api = makeApi(token);
    const controller = new AbortController();
    const uploadTimeoutMs = (() => {
      const MB = 1024 * 1024;
      if (!file?.size) return 45000;
      const approx = 15000 + Math.ceil(file.size / MB) * 4000;
      return Math.min(Math.max(approx, 20000), 90000);
    })();
    const t = setTimeout(() => controller.abort(), uploadTimeoutMs);

    let data;
    try {
      data = await api.raw('/api/media/upload/episode_cover', { method: 'POST', body: fd, signal: controller.signal });
    } catch (e) {
      if (e && e.name === 'AbortError') {
        throw new Error('Cover upload timed out. Please check your connection and try again.');
      }
      throw e;
    } finally {
      clearTimeout(t);
    }

    const uploaded = data?.[0]?.filename;
    if (!uploaded) throw new Error('Cover upload: no filename returned.');
    setEpisodeDetails(prev => ({ ...prev, cover_image_path: uploaded }));
    return uploaded;
  };

  const handleCoverFileSelected = (file) => {
    if (!file) return;
    setEpisodeDetails(prev => ({ ...prev, coverArt: file, coverArtPreview: null, cover_image_path: null }));
    setCoverNeedsUpload(true);
  };

  const handleUploadProcessedCover = async () => {
    if (!episodeDetails.coverArt || !coverCropperRef.current) return;
    try {
      setIsUploadingCover(true);
      const blob = await coverCropperRef.current.getProcessedBlob();
      if (!blob) { throw new Error('Could not process image.'); }
      const processedFile = new File([blob], (episodeDetails.coverArt.name.replace(/\.[^.]+$/, '') + '-square.jpg'), { type: 'image/jpeg' });
      await uploadCover(processedFile);
      const reader = new FileReader();
      reader.onloadend = () => {
        setEpisodeDetails(prev => ({ ...prev, coverArtPreview: reader.result }));
      };
      reader.readAsDataURL(blob);
      setCoverNeedsUpload(false);
      toast({ title: 'Cover saved', description: 'Square cover uploaded.' });
    } catch (e) {
      toast({ variant: 'destructive', title: 'Cover upload failed', description: e.message || String(e) });
    } finally {
      setIsUploadingCover(false);
    }
  };

  const clearCover = useCallback(() => {
    setEpisodeDetails(p => ({ ...p, coverArt: null, coverArtPreview: null, cover_image_path: null, cover_crop: null }));
    setCoverNeedsUpload(false);
  }, [setEpisodeDetails]);

  return {
    mediaLibrary,
    isUploadingCover,
    coverNeedsUpload,
    coverArtInputRef,
    coverCropperRef,
    refreshMediaLibrary,
    handleCoverFileSelected,
    handleUploadProcessedCover,
    clearCover,
  };
}