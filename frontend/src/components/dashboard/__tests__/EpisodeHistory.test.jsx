import React from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import EpisodeHistory from '../EpisodeHistory.jsx';

vi.mock('@/lib/apiClient', () => {
  const episodes = [
    {
      id: 1,
      title: 'Draft Episode',
      status: 'processing',
      final_audio_exists: false,
      _scheduling: false,
      created_at: '2024-01-01T00:00:00Z',
      publish_at: null,
      processed_at: null,
      cover_path: null,
      meta_json: null,
      podcast_id: 99,
    },
  ];
  return {
    makeApi: () => ({
      get: async (path) => {
        if (path.startsWith('/api/episodes/')) {
          return { items: episodes, total: episodes.length };
        }
        return {};
      },
    }),
    isApiError: () => false,
  };
});

vi.mock('@/hooks/useResolvedTimezone', () => ({
  useResolvedTimezone: () => 'UTC',
}));

vi.mock('../EpisodeHistoryPreview.jsx', () => ({
  default: () => null,
}));

describe('EpisodeHistory schedule controls', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('disables schedule button for unprocessed episodes', async () => {
    render(<EpisodeHistory token="test-token" />);

    const scheduleButton = await screen.findByRole('button', { name: /schedule/i });

    await waitFor(() => {
      expect(scheduleButton).toBeDisabled();
    });
  });
});
