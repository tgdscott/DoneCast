const UUID_WITH_DASHES = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const HEXISH = /^[0-9a-f]{20,}$/i;

export function isUuidLike(value) {
  if (!value || typeof value !== 'string') return false;
  const trimmed = value.trim();
  if (!trimmed) return false;
  return UUID_WITH_DASHES.test(trimmed) || HEXISH.test(trimmed);
}

export function formatDisplayName(input, options = {}) {
  const { fallback = '' } = options;

  try {
    let raw = '';

    if (typeof input === 'string') {
      raw = input;
    } else if (input && typeof input === 'object') {
      raw =
        input.friendly_name ??
        input.client_name ??
        input.display_name ??
        input.original_name ??
        input.common_name ??
        input.title ??
        input.name ??
        input.filename ??
        input.file_name ??
        input.id ??
        '';
    }

    if (typeof raw !== 'string') raw = String(raw || '');
    if (!raw) return fallback;

    let cleaned = raw;

    cleaned = cleaned.split(/[\\/]/).pop();
    cleaned = cleaned.replace(/\.[a-z0-9]{2,5}$/i, '');
    cleaned = cleaned.replace(/^(?:[0-9a-f]{8,}|[0-9a-f-]{20,})[_-]+/i, '');
    cleaned = cleaned.replace(/[._-]+/g, ' ');
    cleaned = cleaned.replace(/\s+/g, ' ').trim();

    if (!cleaned || isUuidLike(cleaned)) return fallback;

    cleaned = cleaned
      .split(' ')
      .filter(Boolean)
      .map((word) => word[0].toUpperCase() + word.slice(1))
      .join(' ');

    if (!cleaned || isUuidLike(cleaned)) return fallback;

    return cleaned;
  } catch {
    return fallback;
  }
}

export function ensureDisplayName(input, fallback = '') {
  const formatted = formatDisplayName(input, { fallback: '' });
  if (formatted) return formatted;
  if (typeof input === 'string' && !isUuidLike(input)) return input;
  return fallback;
}
