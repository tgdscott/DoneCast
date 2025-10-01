import { describe, it, expect } from 'vitest';
import { wavInternals } from '@/lib/audioConversion.js';

const { decodeWavHeader, decodePcmSample } = wavInternals;

const createStereo24In32Wav = () => {
  const numChannels = 2;
  const sampleRate = 48000;
  const containerBits = 32;
  const validBits = 24;
  const bytesPerSample = containerBits / 8;
  const blockAlign = numChannels * bytesPerSample;
  const frames = 2;
  const dataSize = frames * blockAlign;
  const fmtChunkSize = 40;
  const totalSize = 12 + 8 + fmtChunkSize + 8 + dataSize;
  const buffer = new ArrayBuffer(totalSize);
  const view = new DataView(buffer);

  const writeFourCC = (position, text) => {
    for (let i = 0; i < 4; i += 1) {
      view.setUint8(position + i, text.charCodeAt(i));
    }
  };

  writeFourCC(0, 'RIFF');
  view.setUint32(4, totalSize - 8, true);
  writeFourCC(8, 'WAVE');

  writeFourCC(12, 'fmt ');
  view.setUint32(16, fmtChunkSize, true);
  const fmtOffset = 20;
  view.setUint16(fmtOffset, 0xfffe, true);
  view.setUint16(fmtOffset + 2, numChannels, true);
  view.setUint32(fmtOffset + 4, sampleRate, true);
  view.setUint32(fmtOffset + 8, sampleRate * blockAlign, true);
  view.setUint16(fmtOffset + 12, blockAlign, true);
  view.setUint16(fmtOffset + 14, containerBits, true);
  view.setUint16(fmtOffset + 16, 22, true);
  view.setUint16(fmtOffset + 18, validBits, true);
  view.setUint32(fmtOffset + 20, 0, true);
  view.setUint32(fmtOffset + 24, 0x00000001, true);
  view.setUint16(fmtOffset + 28, 0x0000, true);
  view.setUint16(fmtOffset + 30, 0x0010, true);
  const data4 = [0x80, 0x00, 0x00, 0xaa, 0x00, 0x38, 0x9b, 0x71];
  data4.forEach((byte, index) => {
    view.setUint8(fmtOffset + 32 + index, byte);
  });

  const dataChunkOffset = 12 + 8 + fmtChunkSize;
  writeFourCC(dataChunkOffset, 'data');
  view.setUint32(dataChunkOffset + 4, dataSize, true);
  const samplesOffset = dataChunkOffset + 8;

  const toContainerValue = (signedValue) => {
    let value = signedValue;
    if (value < 0) {
      value += 2 ** validBits;
    }
    return (value << (containerBits - validBits)) >>> 0;
  };

  const writeSample = (index, signedValue) => {
    let containerValue = toContainerValue(signedValue);
    const sampleOffset = samplesOffset + index * bytesPerSample;
    for (let byteIndex = 0; byteIndex < bytesPerSample; byteIndex += 1) {
      view.setUint8(sampleOffset + byteIndex, containerValue & 0xff);
      containerValue >>>= 8;
    }
  };

  const sampleValues = [0x7fffff, -0x800000, -1, 0];
  sampleValues.forEach((value, index) => writeSample(index, value));

  return buffer;
};

describe('decodeWavHeader with extensible 24-bit PCM', () => {
  it('retains container bit depth and exposes valid bits without altering stride', () => {
    const buffer = createStereo24In32Wav();
    const header = decodeWavHeader(buffer);

    expect(header.numberOfChannels).toBe(2);
    expect(header.bitsPerSample).toBe(32);
    expect(header.validBitsPerSample).toBe(24);
    expect(header.bytesPerSample).toBe(4);
    expect(header.blockAlign).toBe(8);
    expect(header.dataSize).toBe(16);

    const view = new DataView(buffer);
    const firstLeft = decodePcmSample(
      view,
      header.dataOffset,
      header.bytesPerSample,
      header.audioFormat,
      header.validBitsPerSample
    );
    const firstRight = decodePcmSample(
      view,
      header.dataOffset + header.bytesPerSample,
      header.bytesPerSample,
      header.audioFormat,
      header.validBitsPerSample
    );
    const secondLeft = decodePcmSample(
      view,
      header.dataOffset + header.blockAlign,
      header.bytesPerSample,
      header.audioFormat,
      header.validBitsPerSample
    );
    const secondRight = decodePcmSample(
      view,
      header.dataOffset + header.blockAlign + header.bytesPerSample,
      header.bytesPerSample,
      header.audioFormat,
      header.validBitsPerSample
    );

    expect(firstLeft).toBeCloseTo(0x7fffff / 0x800000, 6);
    expect(firstRight).toBeCloseTo(-1, 6);
    expect(secondLeft).toBeCloseTo(-1 / 0x800000, 10);
    expect(secondRight).toBeCloseTo(0, 10);
  });
});
