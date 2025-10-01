import lamejs from 'lamejs';

const hasWindow = typeof window !== 'undefined';
const AudioContextCtor = hasWindow ? window.AudioContext || window.webkitAudioContext : null;

const floatTo16BitPCM = (float32) => {
  const buffer = new Int16Array(float32.length);
  for (let i = 0; i < float32.length; i += 1) {
    const sample = Math.max(-1, Math.min(1, float32[i] || 0));
    buffer[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
  }
  return buffer;
};

const defaultOptions = {
  bitrate: 128,
  minImprovementRatio: 2,
};

export async function convertAudioFileToMp3IfBeneficial(file, options = {}) {
  if (!file) {
    return { file, converted: false, reason: 'no-file' };
  }

  const opts = { ...defaultOptions, ...options };
  const lowerName = (file.name || '').toLowerCase();

  if (file.type === 'audio/mpeg' || lowerName.endsWith('.mp3')) {
    return { file, converted: false, reason: 'already-mp3' };
  }

  if (!AudioContextCtor) {
    return { file, converted: false, reason: 'no-audio-context' };
  }

  const audioContext = new AudioContextCtor();
  try {
    const arrayBuffer = await file.arrayBuffer();
    const audioBuffer = await audioContext.decodeAudioData(arrayBuffer.slice(0));
    const channelCount = Math.max(1, audioBuffer.numberOfChannels || 1);
    const sampleRate = audioBuffer.sampleRate || 44100;

    const left = floatTo16BitPCM(audioBuffer.getChannelData(0));
    const right = channelCount > 1 ? floatTo16BitPCM(audioBuffer.getChannelData(1)) : null;

    const encoder = new lamejs.Mp3Encoder(channelCount > 1 ? 2 : 1, sampleRate, opts.bitrate);
    const blockSize = 1152;
    const mp3Chunks = [];

    for (let i = 0; i < left.length; i += blockSize) {
      const leftChunk = left.subarray(i, Math.min(i + blockSize, left.length));
      let data;
      if (right) {
        const rightChunk = right.subarray(i, Math.min(i + blockSize, right.length));
        data = encoder.encodeBuffer(leftChunk, rightChunk);
      } else {
        data = encoder.encodeBuffer(leftChunk);
      }
      if (data && data.length) {
        mp3Chunks.push(data);
      }
    }

    const end = encoder.flush();
    if (end && end.length) {
      mp3Chunks.push(end);
    }

    const mp3Blob = new Blob(mp3Chunks, { type: 'audio/mpeg' });
    const mp3Size = mp3Blob.size;

    if (!mp3Size) {
      return { file, converted: false, reason: 'encode-failed' };
    }

    if (file.size > mp3Size * opts.minImprovementRatio) {
      const baseName = file.name?.replace(/\.[^/.]+$/, '') || 'audio';
      const mp3File = new File([mp3Blob], `${baseName}.mp3`, {
        type: 'audio/mpeg',
        lastModified: file.lastModified || Date.now(),
      });
      return {
        file: mp3File,
        converted: true,
        originalSize: file.size,
        convertedSize: mp3Size,
        reason: 'converted',
      };
    }

    return {
      file,
      converted: false,
      convertedSize: mp3Size,
      originalSize: file.size,
      reason: 'not-beneficial',
    };
  } catch (error) {
    return { file, converted: false, reason: 'conversion-error', error };
  } finally {
    try {
      await audioContext.close();
    } catch (closeError) {
      console.warn('Failed to close audio context after conversion', closeError);
    }
  }
}
