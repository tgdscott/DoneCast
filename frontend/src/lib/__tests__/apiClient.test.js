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

  it('strips trailing /api for asset paths when base is absolute', async () => {
    vi.stubEnv('VITE_API_BASE', 'https://example.com/api');
    const { assetUrl } = await import('../apiClient.js');
    expect(assetUrl('/static/foo.jpg')).toBe('https://example.com/static/foo.jpg');
  });

  it('retains /api prefix for asset paths when base is relative', async () => {
    vi.stubEnv('VITE_API_BASE', '/api');
    const { assetUrl } = await import('../apiClient.js');
    expect(assetUrl('/static/foo.jpg')).toBe('/api/static/foo.jpg');
    expect(assetUrl('static/foo.jpg')).toBe('/api/static/foo.jpg');
  });
});
