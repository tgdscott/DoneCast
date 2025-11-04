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
    delete globalThis.localStorage;
    delete globalThis.window;
  });

  afterEach(() => {
    resetEnvAndModules();
    delete globalThis.localStorage;
    delete globalThis.window;
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

  it('appends auth token to playback URLs when available', async () => {
    const storage = {
      getItem: vi.fn((key) => (key === 'authToken' ? 'abc123' : null)),
    };
    globalThis.localStorage = storage;
    vi.stubEnv('VITE_API_BASE', '/api');

    const { assetUrl } = await import('../apiClient.js');
    expect(assetUrl('/api/episodes/123/playback')).toBe('/api/episodes/123/playback?token=abc123');
    expect(assetUrl('/api/episodes/123/playback?foo=bar')).toBe('/api/episodes/123/playback?foo=bar&token=abc123');
    expect(assetUrl('/static/foo.jpg')).toBe('/api/static/foo.jpg');
  });
});
