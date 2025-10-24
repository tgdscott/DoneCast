/**
 * Audio utility functions for the recorder
 */

/**
 * Generate a beep sound for countdown
 * @param {number} frequency - Frequency in Hz (default: 800)
 * @param {number} duration - Duration in milliseconds (default: 150)
 */
export const playBeep = (frequency = 800, duration = 150) => {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const oscillator = ctx.createOscillator();
    const gainNode = ctx.createGain();
    
    oscillator.connect(gainNode);
    gainNode.connect(ctx.destination);
    
    oscillator.frequency.value = frequency;
    oscillator.type = 'sine';
    
    gainNode.gain.setValueAtTime(0.3, ctx.currentTime);
    gainNode.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + duration / 1000);
    
    oscillator.start(ctx.currentTime);
    oscillator.stop(ctx.currentTime + duration / 1000);
    
    setTimeout(() => {
      try { ctx.close(); } catch {}
    }, duration + 100);
  } catch (e) {
    // Beeps are optional, ignore errors
    console.log('Beep failed:', e);
  }
};

/**
 * Format seconds as MM:SS
 * @param {number} s - Seconds
 * @returns {string} Formatted time string
 */
export const formatTime = (s) => {
  const m = Math.floor(s / 60)
    .toString()
    .padStart(2, "0");
  const r = Math.floor(s % 60)
    .toString()
    .padStart(2, "0");
  return `${m}:${r}`;
};

/**
 * Pick the best supported MIME type for recording
 * @returns {string} MIME type string or empty string if none supported
 */
export const pickMimeType = () => {
  if (window.MediaRecorder) {
    if (MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported("audio/webm;codecs=opus")) {
      return "audio/webm;codecs=opus";
    }
    if (MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported("audio/mp4;codecs=aac")) {
      return "audio/mp4;codecs=aac"; // Safari/iOS
    }
  }
  return "";
};

/**
 * Re-encode a recording Blob to PCM WAV to normalize timestamps and avoid per-chunk glitches.
 * Returns a Blob of type audio/wav. Throws if decode fails.
 * @param {Blob} blob - Input audio blob
 * @returns {Promise<Blob>} WAV encoded blob
 */
export const reencodeToWav = async (blob) => {
  const arrayBuffer = await blob.arrayBuffer();
  const AC = window.AudioContext || window.webkitAudioContext;
  if (!AC) throw new Error("No AudioContext available");
  const ctx = new AC();
  try {
    const audioBuffer = await ctx.decodeAudioData(arrayBuffer);
    const numChannels = Math.min(2, Math.max(1, audioBuffer.numberOfChannels || 1));
    const sampleRate = audioBuffer.sampleRate;
    const length = audioBuffer.length;
    // Prepare interleaved PCM16
    const channelData = [];
    for (let ch = 0; ch < numChannels; ch++) {
      channelData[ch] = audioBuffer.getChannelData(ch);
    }
    const bytesPerSample = 2;
    const blockAlign = numChannels * bytesPerSample;
    const byteRate = sampleRate * blockAlign;
    const dataSize = length * blockAlign;
    const buffer = new ArrayBuffer(44 + dataSize);
    const view = new DataView(buffer);

    // Write WAV header
    let offset = 0;
    // RIFF identifier 'RIFF'
    view.setUint32(offset, 0x52494646, false); offset += 4;
    // file length minus RIFF and size fields
    view.setUint32(offset, 36 + dataSize, true); offset += 4;
    // RIFF type 'WAVE'
    view.setUint32(offset, 0x57415645, false); offset += 4;
    // format chunk identifier 'fmt '
    view.setUint32(offset, 0x666d7420, false); offset += 4;
    // format chunk length
    view.setUint32(offset, 16, true); offset += 4;
    // audio format (1 = PCM)
    view.setUint16(offset, 1, true); offset += 2;
    // number of channels
    view.setUint16(offset, numChannels, true); offset += 2;
    // sample rate
    view.setUint32(offset, sampleRate, true); offset += 4;
    // byte rate (sample rate * block align)
    view.setUint32(offset, byteRate, true); offset += 4;
    // block align (channel count * bytes per sample)
    view.setUint16(offset, blockAlign, true); offset += 2;
    // bits per sample
    view.setUint16(offset, 16, true); offset += 2;
    // data chunk identifier 'data'
    view.setUint32(offset, 0x64617461, false); offset += 4;
    // data chunk length
    view.setUint32(offset, dataSize, true); offset += 4;

    // PCM samples
    const writeSample = (v) => {
      // Clamp to [-1,1] then scale to 16-bit PCM
      const s = Math.max(-1, Math.min(1, v));
      view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
      offset += 2;
    };

    if (numChannels === 1) {
      for (let i = 0; i < length; i++) {
        writeSample(channelData[0][i]);
      }
    } else {
      for (let i = 0; i < length; i++) {
        for (let ch = 0; ch < numChannels; ch++) {
          writeSample(channelData[ch][i]);
        }
      }
    }

    await ctx.close();
    return new Blob([buffer], { type: "audio/wav" });
  } catch (err) {
    await ctx.close();
    throw err;
  }
};

/**
 * Extract stem (filename without extension) from a filename
 * @param {string} filename - Full filename
 * @returns {string} Filename without extension
 */
export const extractStemFromFilename = (filename) => {
  if (!filename) return "";
  const lastDotIndex = filename.lastIndexOf(".");
  return lastDotIndex > 0 ? filename.substring(0, lastDotIndex) : filename;
};

/**
 * Ensure a name has the specified extension
 * @param {string} name - Base name
 * @param {string} ext - Extension (with or without dot)
 * @returns {string} Name with extension
 */
export const ensureExt = (name, ext) => {
  const e = ext.startsWith(".") ? ext : `.${ext}`;
  return name.toLowerCase().endsWith(e.toLowerCase()) ? name : name + e;
};

/**
 * Generate a timestamp-based filename
 * @returns {string} Formatted date string
 */
export const formatDateName = () => {
  const now = new Date();
  const yyyy = now.getFullYear();
  const mm = String(now.getMonth() + 1).padStart(2, "0");
  const dd = String(now.getDate()).padStart(2, "0");
  const hh = String(now.getHours()).padStart(2, "0");
  const min = String(now.getMinutes()).padStart(2, "0");
  const ss = String(now.getSeconds()).padStart(2, "0");
  return `recording-${yyyy}${mm}${dd}-${hh}${min}${ss}`;
};

/**
 * Detect if the current device is mobile
 * @returns {boolean}
 */
export const isMobileDevice = () => {
  try {
    return /Mobi|Android|iPhone|iPad|iPod/i.test(navigator.userAgent || '');
  } catch {
    return false;
  }
};
