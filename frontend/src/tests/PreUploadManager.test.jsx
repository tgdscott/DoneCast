import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import PreUploadManager from '@/components/dashboard/PreUploadManager';
import { loadPublicConfig, resetPublicConfigCache } from '@/hooks/usePublicConfig';

const { rawMock, makeApiMock } = vi.hoisted(() => {
  const raw = vi.fn().mockResolvedValue({});
  const makeApi = vi.fn(() => ({ raw }));
  return { rawMock: raw, makeApiMock: makeApi };
});

const { toastMock } = vi.hoisted(() => ({ toastMock: vi.fn() }));

const { convertMock } = vi.hoisted(() => ({ convertMock: vi.fn() }));

const { resizeObserverMock } = vi.hoisted(() => ({
  resizeObserverMock: vi.fn(() => ({
    observe: vi.fn(),
    unobserve: vi.fn(),
    disconnect: vi.fn(),
  })),
}));

vi.mock('@/lib/apiClient', () => ({
  makeApi: makeApiMock,
  buildApiUrl: (path) => path,
}));

vi.mock('@/hooks/use-toast', () => ({
  useToast: () => ({ toast: toastMock }),
}));

vi.mock('@/lib/audioConversion', () => ({
  convertAudioFileToMp3IfBeneficial: (...args) => convertMock(...args),
}));

const server = setupServer(
  http.get('/api/public/config', () => HttpResponse.json({ browser_audio_conversion_enabled: true })),
);

const originalXMLHttpRequest = global.XMLHttpRequest;
const originalResizeObserver = global.ResizeObserver;

beforeAll(() => {
  server.listen();
  global.ResizeObserver = resizeObserverMock;
});

afterAll(() => {
  global.XMLHttpRequest = originalXMLHttpRequest;
  global.ResizeObserver = originalResizeObserver;
  server.close();
});

beforeEach(() => {
  global.XMLHttpRequest = undefined;
});

afterEach(() => {
  server.resetHandlers();
  resetPublicConfigCache();
  rawMock.mockClear();
  makeApiMock.mockClear();
  toastMock.mockClear();
  convertMock.mockClear();
  resizeObserverMock.mockClear();
});

const renderComponent = (props = {}) =>
  render(
    <PreUploadManager
      token="test-token"
      onBack={vi.fn()}
      onDone={props.onDone || vi.fn()}
      onUploaded={props.onUploaded || vi.fn()}
      defaultEmail="tester@example.com"
    />,
  );

describe('PreUploadManager', () => {
  it('skips conversion when browser flag is disabled and uploads original file', async () => {
    server.use(
      http.get('/api/public/config', () =>
        HttpResponse.json({ browser_audio_conversion_enabled: false }),
      ),
    );
    await loadPublicConfig({ force: true });
    const onDone = vi.fn();
    const onUploaded = vi.fn();

    renderComponent({ onDone, onUploaded });

    const fileInput = screen.getByLabelText(/drag & drop or click to choose an audio file/i);
    const file = new File(['audio'], 'episode.wav', { type: 'audio/wav' });
    await act(async () => {
      Object.defineProperty(fileInput, 'files', {
        value: [file],
        configurable: true,
      });
      fireEvent.change(fileInput);
    });

    await screen.findByText(/browser-based audio conversion is disabled/i);

    const friendlyNameInput = screen.getByPlaceholderText(/my episode draft/i);
    fireEvent.change(friendlyNameInput, { target: { value: 'Episode 1' } });

    const uploadButton = screen.getByRole('button', { name: /upload and return/i });
    fireEvent.click(uploadButton);

    expect(convertMock).not.toHaveBeenCalled();

    await waitFor(() => {
      expect(makeApiMock).toHaveBeenCalledTimes(1);
      expect(rawMock).toHaveBeenCalledTimes(1);
    });

    expect(onDone).toHaveBeenCalled();
    await waitFor(() => {
      expect(onUploaded).toHaveBeenCalled();
    });
  });

  it('converts audio when browser flag is enabled', async () => {
    convertMock.mockResolvedValue({
      converted: true,
      file: new File(['converted'], 'episode.mp3', { type: 'audio/mpeg' }),
      originalSize: 2048,
      convertedSize: 1024,
    });

    const onDone = vi.fn();
    const onUploaded = vi.fn();

    await loadPublicConfig({ force: true });
    renderComponent({ onDone, onUploaded });

    const fileInput = screen.getByLabelText(/drag & drop or click to choose an audio file/i);
    const file = new File(['audio'], 'episode.wav', { type: 'audio/wav' });
    await act(async () => {
      Object.defineProperty(fileInput, 'files', {
        value: [file],
        configurable: true,
      });
      fireEvent.change(fileInput);
    });

    await waitFor(() => {
      expect(convertMock).toHaveBeenCalledTimes(1);
    });

    await screen.findByText(/converted to mp3 for upload/i);

    const friendlyNameInput = screen.getByPlaceholderText(/my episode draft/i);
    fireEvent.change(friendlyNameInput, { target: { value: 'Episode 2' } });

    const uploadButton = screen.getByRole('button', { name: /upload and return/i });
    fireEvent.click(uploadButton);

    await waitFor(() => {
      expect(makeApiMock).toHaveBeenCalledTimes(1);
      expect(rawMock).toHaveBeenCalledTimes(1);
    });

    expect(onDone).toHaveBeenCalled();
    await waitFor(() => {
      expect(onUploaded).toHaveBeenCalled();
    });
  });
});
