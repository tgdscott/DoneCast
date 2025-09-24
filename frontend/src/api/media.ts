export type CreateTTSPayload = {
  text: string;
  voice_id?: string;
  provider?: 'elevenlabs' | 'google';
  google_voice?: string;
  speaking_rate?: number;
  category: 'intro' | 'outro' | 'commercial' | 'sfx' | 'music';
  friendly_name?: string;
  confirm_charge?: boolean;
};

export type MediaItemDTO = {
  id: string;
  filename: string;
  friendly_name?: string;
  category: string;
  filesize?: number;
};

function friendlyMessage(status: number, raw: any): string {
  try {
    const j = typeof raw === 'string' ? JSON.parse(raw) : raw;
    const detail = j?.detail || j?.error || j?.message;
    if (detail) return String(detail);
  } catch {}
  if (status === 401 || status === 403) return 'You are not signed in or your session has expired.';
  if (status === 429) return 'Too many requests. Please slow down and try again shortly.';
  if (status >= 500) return 'The server had a problem creating speech. Please try again.';
  return 'Request failed. Please check your input and try again.';
}

import { makeApi } from '@/lib/apiClient';

export async function createTTS(payload: CreateTTSPayload): Promise<MediaItemDTO> {
  const r = await makeApi().post('/api/media/tts', payload);
  const data = r;
  // Some backends wrap payloads; normalize the common cases
  const item = Array.isArray(data) ? data[0] : (data?.item || data);
  if (!item?.filename) throw new Error('TTS succeeded but no file was returned.');
  return item as MediaItemDTO;
}
