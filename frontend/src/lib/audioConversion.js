import lamejs from 'lamejs';
import LameModule from 'lamejs/src/js/Lame.js';
import MPEGModeModule from 'lamejs/src/js/MPEGMode.js';
import BitStreamModule from 'lamejs/src/js/BitStream.js';

const MPEGMode = MPEGModeModule?.default || MPEGModeModule;
const Lame = LameModule?.default || LameModule;
const BitStream = BitStreamModule?.default || BitStreamModule;

if (typeof globalThis !== 'undefined') {
  const globalScope = globalThis;
  if (globalScope) {
    if (!globalScope.MPEGMode && MPEGMode) {
      globalScope.MPEGMode = MPEGMode;
    }
    if (!globalScope.Lame && Lame) {
      globalScope.Lame = Lame;
    }
    if (!globalScope.BitStream && BitStream) {
      globalScope.BitStream = BitStream;
    }
  }
}

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

// Yield between chunks so the UI remains responsive. Use a timer instead of
// requestAnimationFrame so work continues when the tab is hidden (rAF can be
// throttled to 1fps or paused entirely in background tabs across browsers).
const yieldToEventLoop = () =>
  new Promise((resolve) => {
    setTimeout(resolve, 0);
  });

const SUPPORTED_MP3_SAMPLE_RATES = [48000, 44100, 32000, 24000, 22050, 16000, 12000, 11025, 8000];

const clampSampleRateForMp3 = (sampleRate) => {
  if (!Number.isFinite(sampleRate) || sampleRate <= 0) {
    return 44100;
  }
  for (let i = 0; i < SUPPORTED_MP3_SAMPLE_RATES.length; i += 1) {
    const allowed = SUPPORTED_MP3_SAMPLE_RATES[i];
    if (sampleRate >= allowed) {
      return allowed;
    }
  }
  return SUPPORTED_MP3_SAMPLE_RATES[SUPPORTED_MP3_SAMPLE_RATES.length - 1];
};

const resampleFloat32Channel = (input, sourceRate, targetRate) => {
  if (!input || sourceRate === targetRate) {
    return input;
  }
  if (!Number.isFinite(sourceRate) || !Number.isFinite(targetRate) || sourceRate <= 0 || targetRate <= 0) {
    return input;
  }

  const ratio = sourceRate / targetRate;
  const sourceLength = input.length;
  if (!sourceLength) {
    return input;
  }

  const outputLength = Math.max(1, Math.floor((sourceLength - 1) / ratio) + 1);
  const output = new Float32Array(outputLength);
  for (let i = 0; i < outputLength; i += 1) {
    const sourceIndex = i * ratio;
    const index0 = Math.min(sourceLength - 1, Math.max(0, Math.floor(sourceIndex)));
    const index1 = Math.min(sourceLength - 1, index0 + 1);
    const frac = sourceIndex - index0;
    const sample0 = input[index0] ?? 0;
    const sample1 = input[index1] ?? sample0;
    output[i] = sample0 + (sample1 - sample0) * frac;
  }
  return output;
};

const resampleFloat32ChannelData = (channelData, sourceRate, targetRate) => {
  if (!channelData || !channelData.length || sourceRate === targetRate) {
    return channelData;
  }
  return channelData.map((channel) => resampleFloat32Channel(channel, sourceRate, targetRate));
};

const createStreamingResampler = (sourceRate, targetRate, channelCount) => {
  if (!Number.isFinite(sourceRate) || sourceRate <= 0 || !Number.isFinite(targetRate) || targetRate <= 0) {
    return {
      processSample(sample, _index, emit) {
        const out = new Array(channelCount);
        for (let i = 0; i < channelCount; i += 1) {
          out[i] = sample[i] ?? sample[sample.length - 1] ?? 0;
        }
        emit(out);
      },
      finalize() {},
    };
  }

  if (Math.abs(sourceRate - targetRate) < 1e-6) {
    return {
      processSample(sample, _index, emit) {
        const out = new Array(channelCount);
        for (let i = 0; i < channelCount; i += 1) {
          out[i] = sample[i] ?? sample[sample.length - 1] ?? 0;
        }
        emit(out);
      },
      finalize() {},
    };
  }

  const ratio = sourceRate / targetRate;
  let nextOutputPosition = 0;
  let prevSamples = new Array(channelCount).fill(0);
  let prevIndex = 0;
  let hasPrev = false;

  return {
    processSample(sample, absoluteIndex, emit) {
      const currentSamples = new Array(channelCount);
      for (let i = 0; i < channelCount; i += 1) {
        currentSamples[i] = sample[i] ?? sample[sample.length - 1] ?? 0;
      }

      if (!hasPrev) {
        prevSamples = currentSamples.slice();
        prevIndex = absoluteIndex;
        hasPrev = true;
      }

      const span = absoluteIndex - prevIndex;
      const epsilon = 1e-7;
      while (nextOutputPosition <= absoluteIndex + epsilon) {
        let output;
        if (!hasPrev || span <= 0) {
          output = currentSamples.slice();
        } else {
          const rawPosition = (nextOutputPosition - prevIndex) / span;
          const position = Math.max(0, Math.min(1, rawPosition));
          output = new Array(channelCount);
          for (let i = 0; i < channelCount; i += 1) {
            const prevValue = prevSamples[i];
            const currValue = currentSamples[i];
            output[i] = prevValue + (currValue - prevValue) * position;
          }
        }
        emit(output);
        nextOutputPosition += ratio;
      }

      prevSamples = currentSamples.slice();
      prevIndex = absoluteIndex;
    },
    finalize(totalFrames, emit) {
      if (!hasPrev) {
        return;
      }
      const lastIndex = Math.max(0, totalFrames - 1);
      const epsilon = 1e-7;
      while (nextOutputPosition <= lastIndex + epsilon) {
        emit(prevSamples.slice());
        nextOutputPosition += ratio;
      }
    },
  };
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

const decodePcmSample = (view, offset, bytesPerSample, audioFormat, validBitsPerSample) => {
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

  const containerBits = bytesPerSample * 8;
  const effectiveBits = Math.max(
    1,
    Math.min(containerBits, Number.isFinite(validBitsPerSample) && validBitsPerSample > 0 ? validBitsPerSample : containerBits)
  );

  switch (bytesPerSample) {
    case 1: {
      return (view.getUint8(offset) - 128) / 128;
    }
    case 2: {
      let value = view.getInt16(offset, true);
      const shift = containerBits - effectiveBits;
      if (shift > 0) {
        value >>= shift;
      }
      return value / (2 ** (effectiveBits - 1));
    }
    case 3: {
      const b0 = view.getUint8(offset);
      const b1 = view.getUint8(offset + 1);
      const b2 = view.getUint8(offset + 2);
      let value = (b2 << 16) | (b1 << 8) | b0;
      if (value & 0x800000) {
        value |= 0xff000000;
      }
      const shift = containerBits - effectiveBits;
      if (shift > 0) {
        value >>= shift;
      }
      return value / (2 ** (effectiveBits - 1));
    }
    case 4: {
      let value = view.getInt32(offset, true);
      const shift = containerBits - effectiveBits;
      if (shift > 0) {
        value >>= shift;
      }
      return value / (2 ** (effectiveBits - 1));
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
      const containerBitsPerSample = view.getUint16(chunkDataOffset + 14, true);
      let effectiveFormat = audioFormat;
      let validBitsPerSample = null;

      if (chunkSize >= 18) {
        const extensionSize = view.getUint16(chunkDataOffset + 16, true);
        // Guard against truncated fmt chunks
        const availableExtensionBytes = Math.max(0, Math.min(extensionSize, chunkSize - 18));
        if (audioFormat === 0xfffe /* WAVE_FORMAT_EXTENSIBLE */ && availableExtensionBytes >= 22) {
          try {
            const validBits = view.getUint16(chunkDataOffset + 18, true);
            if (validBits) {
              validBitsPerSample = validBits;
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
        bitsPerSample: containerBitsPerSample,
        validBitsPerSample: validBitsPerSample ?? containerBitsPerSample,
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

  const { audioFormat, numberOfChannels, sampleRate, blockAlign, bitsPerSample, validBitsPerSample } = fmt;
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
    validBitsPerSample,
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

const encodeMp3 = (channelData, inputSampleRate, opts, originalFile) => {
  const hasStereoInput = Array.isArray(channelData) && channelData.length > 1 && channelData[1];
  const targetSampleRate = clampSampleRateForMp3(inputSampleRate || 44100);
  const effectiveData =
    targetSampleRate === inputSampleRate
      ? channelData
      : resampleFloat32ChannelData(channelData, inputSampleRate || 44100, targetSampleRate);
  const leftSource = effectiveData?.[0];
  if (!leftSource) {
    return { file: originalFile, converted: false, reason: 'decode-failed' };
  }
  const left = floatTo16BitPCM(leftSource);
  const hasStereoOutput = hasStereoInput && effectiveData?.[1];
  const right = hasStereoOutput ? floatTo16BitPCM(effectiveData[1]) : null;

  const encoder = new lamejs.Mp3Encoder(hasStereoOutput ? 2 : 1, targetSampleRate, opts.bitrate);
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

const convertWavPcmToMp3 = async (arrayBuffer, opts, originalFile) => {
  const header = decodeWavHeader(arrayBuffer);
  const {
    audioFormat,
    numberOfChannels,
    sampleRate,
    blockAlign,
    bytesPerSample,
    validBitsPerSample,
    dataOffset,
    dataSize,
  } = header;

  const encodeChannels = numberOfChannels > 1 ? 2 : 1;
  const targetSampleRate = clampSampleRateForMp3(sampleRate);
  const encoder = new lamejs.Mp3Encoder(encodeChannels, targetSampleRate, opts.bitrate);
  const mp3Chunks = [];
  const view = new DataView(arrayBuffer);
  const framesPerChunk = 1152 * 20;
  const totalFrames = Math.floor(dataSize / blockAlign);
  let framesProcessed = 0;
  let offset = dataOffset;

  const resampler = createStreamingResampler(sampleRate, targetSampleRate, encodeChannels);

  const emitProgress = (info) => {
    if (typeof opts?.onProgress !== 'function') {
      return;
    }
    try {
      const payload = { phase: 'encoding', totalFrames, framesProcessed, ...(info || {}) };
      if (Number.isFinite(payload.progress)) {
        payload.progress = Math.max(0, Math.min(1, payload.progress));
      }
      opts.onProgress(payload);
    } catch (error) {
      console.warn('convertWavPcmToMp3 progress callback failed', error);
    }
  };

  while (framesProcessed < totalFrames && offset + blockAlign <= view.byteLength) {
    const remainingFrames = totalFrames - framesProcessed;
    const framesThisChunk = Math.max(1, Math.min(framesPerChunk, remainingFrames));
    let chunkLeft = [];
    let chunkRight = encodeChannels === 2 ? [] : null;
    const emitSample = (values) => {
      if (!values || !values.length) {
        return;
      }
      chunkLeft.push(clampAndScaleToInt16(values[0]));
      if (chunkRight) {
        const rightValue = values[1] ?? values[0];
        chunkRight.push(clampAndScaleToInt16(rightValue));
      }
    };

    for (let frame = 0; frame < framesThisChunk; frame += 1) {
      const frameOffset = offset + frame * blockAlign;
      let aggregated;
      if (encodeChannels === 1) {
        let sum = 0;
        for (let channelIndex = 0; channelIndex < numberOfChannels; channelIndex += 1) {
          const sampleOffset = frameOffset + channelIndex * bytesPerSample;
          const pcm = decodePcmSample(
            view,
            sampleOffset,
            bytesPerSample,
            audioFormat,
            validBitsPerSample
          );
          sum += pcm;
        }
        aggregated = [sum / numberOfChannels];
      } else {
        let sumLeft = 0;
        let sumRight = 0;
        let countLeft = 0;
        let countRight = 0;
        for (let channelIndex = 0; channelIndex < numberOfChannels; channelIndex += 1) {
          const sampleOffset = frameOffset + channelIndex * bytesPerSample;
          const pcm = decodePcmSample(
            view,
            sampleOffset,
            bytesPerSample,
            audioFormat,
            validBitsPerSample
          );
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
        aggregated = [leftAvg, rightAvg];
      }
      resampler.processSample(aggregated, framesProcessed + frame, emitSample);
    }

    if (chunkLeft.length) {
      const leftChunk = Int16Array.from(chunkLeft);
      const rightChunk = chunkRight ? Int16Array.from(chunkRight) : null;
      const encoded = rightChunk ? encoder.encodeBuffer(leftChunk, rightChunk) : encoder.encodeBuffer(leftChunk);
      if (encoded && encoded.length) {
        mp3Chunks.push(encoded);
      }
    }

    framesProcessed += framesThisChunk;
    offset += framesThisChunk * blockAlign;

    emitProgress({ progress: totalFrames ? framesProcessed / totalFrames : 0 });
    if (framesProcessed < totalFrames) {
      await yieldToEventLoop();
    }
  }

  let remainingLeft = [];
  let remainingRight = encodeChannels === 2 ? [] : null;
  const emitRemaining = (values) => {
    if (!values || !values.length) {
      return;
    }
    remainingLeft.push(clampAndScaleToInt16(values[0]));
    if (remainingRight) {
      const rightValue = values[1] ?? values[0];
      remainingRight.push(clampAndScaleToInt16(rightValue));
    }
  };

  resampler.finalize(totalFrames, emitRemaining);
  if (remainingLeft.length) {
    const leftChunk = Int16Array.from(remainingLeft);
    const rightChunk = remainingRight ? Int16Array.from(remainingRight) : null;
    const encoded = rightChunk ? encoder.encodeBuffer(leftChunk, rightChunk) : encoder.encodeBuffer(leftChunk);
    if (encoded && encoded.length) {
      mp3Chunks.push(encoded);
    }
  }

  const end = encoder.flush();
  if (end && end.length) {
    mp3Chunks.push(end);
  }

  emitProgress({ progress: 1 });

  return finalizeMp3Encoding(mp3Chunks, opts, originalFile);
};

export const wavInternals = {
  decodeWavHeader,
  decodePcmSample,
};

export async function convertAudioFileToMp3IfBeneficial(file, options = {}) {
  if (!file) {
    return { file, converted: false, reason: 'no-file' };
  }

  const { onProgress, ...optionOverrides } = options || {};
  const opts = { ...defaultOptions, ...optionOverrides };
  if (typeof onProgress === 'function') {
    opts.onProgress = onProgress;
  }
  const reportProgress = (info) => {
    if (typeof opts.onProgress !== 'function') {
      return;
    }
    try {
      const payload = { ...(info || {}) };
      if (Number.isFinite(payload.progress)) {
        payload.progress = Math.max(0, Math.min(1, payload.progress));
      }
      opts.onProgress(payload);
    } catch (error) {
      console.warn('convertAudioFileToMp3IfBeneficial progress callback failed', error);
    }
  };
  const lowerName = (file.name || '').toLowerCase();

  if (file.type === 'audio/mpeg' || lowerName.endsWith('.mp3')) {
    return { file, converted: false, reason: 'already-mp3' };
  }

  let audioContext = null;
  let channelData;
  let sampleRate;

  try {
    const arrayBuffer = await file.arrayBuffer();
    reportProgress({ phase: 'loading', progress: 0 });
    if (isLikelyWavFile(file, arrayBuffer)) {
      try {
        const result = await convertWavPcmToMp3(arrayBuffer, opts, file);
        reportProgress({ phase: 'done', progress: 1 });
        return result;
      } catch (wavError) {
        console.warn('Failed to parse WAV file, falling back to AudioContext', wavError);
      }
    }

    if (!channelData) {
      if (!AudioContextCtor) {
        return { file, converted: false, reason: 'no-audio-context' };
      }
      audioContext = new AudioContextCtor();
      reportProgress({ phase: 'decoding', progress: 0 });
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

    const result = encodeMp3(channelData, sampleRate, opts, file);
    reportProgress({ phase: 'done', progress: 1 });
    return result;
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
