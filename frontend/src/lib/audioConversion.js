import lamejs from 'lamejs';

const hasWindow = typeof window !== 'undefined';
const AudioContextCtor = hasWindow ? window.AudioContext || window.webkitAudioContext : null;

const clampAndScaleToInt16 = (sample) => {
  const clamped = Math.max(-1, Math.min(1, sample || 0));
  const scaled = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
  return Math.round(scaled);
};

const floatTo16BitPCM = (float32) => {
  const buffer = new Int16Array(float32.length);
  for (let i = 0; i < float32.length; i += 1) {
    buffer[i] = clampAndScaleToInt16(float32[i]);
  }
  return buffer;
};

const defaultOptions = {
  bitrate: 128,
  minImprovementRatio: 2,
};

const readFourCC = (view, offset) =>
  String.fromCharCode(view.getUint8(offset), view.getUint8(offset + 1), view.getUint8(offset + 2), view.getUint8(offset + 3));

const isLikelyWavFile = (file, arrayBuffer) => {
  const name = (file?.name || '').toLowerCase();
  const type = (file?.type || '').toLowerCase();
  if (type.includes('wav') || name.endsWith('.wav')) {
    return true;
  }
  if (!arrayBuffer || arrayBuffer.byteLength < 12) {
    return false;
  }
  try {
    const view = new DataView(arrayBuffer, 0, 12);
    const riff = readFourCC(view, 0);
    const wave = readFourCC(view, 8);
    return riff === 'RIFF' && wave === 'WAVE';
  } catch {
    return false;
  }
};

const decodePcmSample = (view, offset, bytesPerSample, audioFormat) => {
  if (audioFormat === 3) {
    // IEEE float
    if (bytesPerSample === 4) {
      return view.getFloat32(offset, true);
    }
    if (bytesPerSample === 8) {
      return view.getFloat64(offset, true);
    }
    throw new Error(`Unsupported float PCM bytes per sample: ${bytesPerSample}`);
  }

  switch (bytesPerSample) {
    case 1: {
      return (view.getUint8(offset) - 128) / 128;
    }
    case 2: {
      return view.getInt16(offset, true) / 0x8000;
    }
    case 3: {
      const b0 = view.getUint8(offset);
      const b1 = view.getUint8(offset + 1);
      const b2 = view.getUint8(offset + 2);
      let value = (b2 << 16) | (b1 << 8) | b0;
      if (value & 0x800000) {
        value |= 0xff000000;
      }
      return value / 0x800000;
    }
    case 4: {
      return view.getInt32(offset, true) / 0x80000000;
    }
    default:
      throw new Error(`Unsupported PCM bytes per sample: ${bytesPerSample}`);
  }
};

const decodeWavHeader = (arrayBuffer) => {
  const view = new DataView(arrayBuffer);
  if (readFourCC(view, 0) !== 'RIFF' || readFourCC(view, 8) !== 'WAVE') {
    throw new Error('Not a RIFF/WAVE file');
  }

  let offset = 12;
  let fmt = null;
  let data = null;

  while (offset + 8 <= view.byteLength && (!fmt || !data)) {
    const chunkId = readFourCC(view, offset);
    const chunkSize = view.getUint32(offset + 4, true);
    const chunkDataOffset = offset + 8;
    if (chunkId === 'fmt ') {
      const audioFormat = view.getUint16(chunkDataOffset, true);
      const numberOfChannels = view.getUint16(chunkDataOffset + 2, true);
      const sampleRate = view.getUint32(chunkDataOffset + 4, true);
      const byteRate = view.getUint32(chunkDataOffset + 8, true);
      const blockAlign = view.getUint16(chunkDataOffset + 12, true);
      const bitsPerSample = view.getUint16(chunkDataOffset + 14, true);
      let effectiveFormat = audioFormat;
      let effectiveBitsPerSample = bitsPerSample;

      if (chunkSize >= 18) {
        const extensionSize = view.getUint16(chunkDataOffset + 16, true);
        // Guard against truncated fmt chunks
        const availableExtensionBytes = Math.max(0, Math.min(extensionSize, chunkSize - 18));
        if (audioFormat === 0xfffe /* WAVE_FORMAT_EXTENSIBLE */ && availableExtensionBytes >= 22) {
          try {
            const validBits = view.getUint16(chunkDataOffset + 18, true);
            if (validBits) {
              effectiveBitsPerSample = validBits;
            }
          } catch {
            /* no-op */
          }
          try {
            const subFormat = view.getUint32(chunkDataOffset + 24, true);
            if (subFormat === 0x00000001) {
              effectiveFormat = 1; // PCM
            } else if (subFormat === 0x00000003) {
              effectiveFormat = 3; // IEEE float
            }
          } catch {
            /* no-op */
          }
        }
      }

      fmt = {
        audioFormat: effectiveFormat,
        numberOfChannels,
        sampleRate,
        byteRate,
        blockAlign,
        bitsPerSample: effectiveBitsPerSample,
      };
    } else if (chunkId === 'data') {
      data = {
        offset: chunkDataOffset,
        size: chunkSize,
      };
    }
    // Chunks are word aligned
    offset = chunkDataOffset + chunkSize + (chunkSize % 2);
  }

  if (!fmt || !data) {
    throw new Error('Incomplete WAV file');
  }

  const { audioFormat, numberOfChannels, sampleRate, blockAlign, bitsPerSample } = fmt;
  if (!numberOfChannels || !sampleRate || !bitsPerSample) {
    throw new Error('Unsupported WAV metadata');
  }
  if (audioFormat !== 1 && audioFormat !== 3) {
    throw new Error(`Unsupported WAV encoding: ${audioFormat}`);
  }

  const bytesPerSample = bitsPerSample / 8;
  if (!Number.isInteger(bytesPerSample) || !bytesPerSample) {
    throw new Error('Invalid bits per sample');
  }

  const sampleCount = Math.floor(data.size / blockAlign);
  if (!sampleCount) {
    throw new Error('WAV file contains no audio data');
  }

  return {
    audioFormat,
    numberOfChannels,
    sampleRate,
    blockAlign,
    bitsPerSample,
    bytesPerSample,
    dataOffset: data.offset,
    dataSize: data.size,
  };
};

const finalizeMp3Encoding = (mp3Chunks, opts, originalFile) => {
  const mp3Blob = new Blob(mp3Chunks, { type: 'audio/mpeg' });
  const mp3Size = mp3Blob.size;

  if (!mp3Size) {
    return { file: originalFile, converted: false, reason: 'encode-failed' };
  }

  if (originalFile.size > mp3Size * opts.minImprovementRatio) {
    const baseName = originalFile.name?.replace(/\.[^/.]+$/, '') || 'audio';
    const mp3File = new File([mp3Blob], `${baseName}.mp3`, {
      type: 'audio/mpeg',
      lastModified: originalFile.lastModified || Date.now(),
    });
    return {
      file: mp3File,
      converted: true,
      originalSize: originalFile.size,
      convertedSize: mp3Size,
      reason: 'converted',
    };
  }

  return {
    file: originalFile,
    converted: false,
    convertedSize: mp3Size,
    originalSize: originalFile.size,
    reason: 'not-beneficial',
  };
};

const encodeMp3 = (channelData, sampleRate, opts, originalFile) => {
  const channelCount = Math.max(1, channelData.length || 1);
  const left = floatTo16BitPCM(channelData[0]);
  const right = channelCount > 1 ? floatTo16BitPCM(channelData[1]) : null;

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

  return finalizeMp3Encoding(mp3Chunks, opts, originalFile);
};

const convertWavPcmToMp3 = (arrayBuffer, opts, originalFile) => {
  const header = decodeWavHeader(arrayBuffer);
  const {
    audioFormat,
    numberOfChannels,
    sampleRate,
    blockAlign,
    bytesPerSample,
    dataOffset,
    dataSize,
  } = header;

  const encodeChannels = numberOfChannels > 1 ? 2 : 1;
  const encoder = new lamejs.Mp3Encoder(encodeChannels, sampleRate, opts.bitrate);
  const mp3Chunks = [];
  const view = new DataView(arrayBuffer);
  const framesPerChunk = 1152 * 20;
  const totalFrames = Math.floor(dataSize / blockAlign);
  let framesProcessed = 0;
  let offset = dataOffset;

  while (framesProcessed < totalFrames && offset + blockAlign <= view.byteLength) {
    const remainingFrames = totalFrames - framesProcessed;
    const framesThisChunk = Math.max(1, Math.min(framesPerChunk, remainingFrames));
    const left = new Int16Array(framesThisChunk);
    const right = encodeChannels === 2 ? new Int16Array(framesThisChunk) : null;

    for (let frame = 0; frame < framesThisChunk; frame += 1) {
      const frameOffset = offset + frame * blockAlign;
      if (encodeChannels === 1) {
        let sum = 0;
        for (let channelIndex = 0; channelIndex < numberOfChannels; channelIndex += 1) {
          const sampleOffset = frameOffset + channelIndex * bytesPerSample;
          const pcm = decodePcmSample(view, sampleOffset, bytesPerSample, audioFormat);
          sum += pcm;
        }
        const averaged = sum / numberOfChannels;
        left[frame] = clampAndScaleToInt16(averaged);
      } else {
        let sumLeft = 0;
        let sumRight = 0;
        let countLeft = 0;
        let countRight = 0;
        for (let channelIndex = 0; channelIndex < numberOfChannels; channelIndex += 1) {
          const sampleOffset = frameOffset + channelIndex * bytesPerSample;
          const pcm = decodePcmSample(view, sampleOffset, bytesPerSample, audioFormat);
          if (channelIndex % 2 === 0) {
            sumLeft += pcm;
            countLeft += 1;
          } else {
            sumRight += pcm;
            countRight += 1;
          }
        }
        const leftAvg = sumLeft / (countLeft || numberOfChannels);
        const rightAvg = countRight ? sumRight / countRight : leftAvg;
        left[frame] = clampAndScaleToInt16(leftAvg);
        right[frame] = clampAndScaleToInt16(rightAvg);
      }
    }

    const encoded = right ? encoder.encodeBuffer(left, right) : encoder.encodeBuffer(left);
    if (encoded && encoded.length) {
      mp3Chunks.push(encoded);
    }

    framesProcessed += framesThisChunk;
    offset += framesThisChunk * blockAlign;
  }

  const end = encoder.flush();
  if (end && end.length) {
    mp3Chunks.push(end);
  }

  return finalizeMp3Encoding(mp3Chunks, opts, originalFile);
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

  let audioContext = null;
  let channelData;
  let sampleRate;

  try {
    const arrayBuffer = await file.arrayBuffer();
    if (isLikelyWavFile(file, arrayBuffer)) {
      try {
        return convertWavPcmToMp3(arrayBuffer, opts, file);
      } catch (wavError) {
        console.warn('Failed to parse WAV file, falling back to AudioContext', wavError);
      }
    }

    if (!channelData) {
      if (!AudioContextCtor) {
        return { file, converted: false, reason: 'no-audio-context' };
      }
      audioContext = new AudioContextCtor();
      const audioBuffer = await audioContext.decodeAudioData(arrayBuffer.slice(0));
      const channelCount = Math.max(1, audioBuffer.numberOfChannels || 1);
      sampleRate = audioBuffer.sampleRate || 44100;
      channelData = Array.from({ length: channelCount }, (_, index) => audioBuffer.getChannelData(index));
    }

    if (!channelData || !channelData[0]) {
      return { file, converted: false, reason: 'decode-failed' };
    }

    if (!sampleRate) {
      sampleRate = 44100;
    }

    return encodeMp3(channelData, sampleRate, opts, file);
  } catch (error) {
    return { file, converted: false, reason: 'conversion-error', error };
  } finally {
    if (audioContext) {
      try {
        await audioContext.close();
      } catch (closeError) {
        console.warn('Failed to close audio context after conversion', closeError);
      }
    }
  }
}
