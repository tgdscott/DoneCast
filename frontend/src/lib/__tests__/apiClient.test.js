import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const resetEnvAndModules = () => {
  if (typeof vi.unstubAllEnvs === 'function') {
    vi.unstubAllEnvs();
  }
  vi.resetModules();
};

describe('apiClient assetUrl', () => {
  beforeEach(() => {
    resetEnvAndModules();
  });

  afterEach(() => {
    resetEnvAndModules();
  });

  it('strips trailing /api for asset paths', async () => {
    vi.stubEnv('VITE_API_BASE', 'https://example.com/api');
    const { assetUrl } = await import('../apiClient.js');
    expect(assetUrl('/static/foo.jpg')).toBe('https://example.com/static/foo.jpg');
  });
});
