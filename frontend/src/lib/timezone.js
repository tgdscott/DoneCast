const DEFAULT_TIMEZONE = 'UTC';

const ensureString = (value) => {
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  return trimmed.length ? trimmed : null;
};

const isValidTimezone = (tz) => {
  const candidate = ensureString(tz);
  if (!candidate) return false;
  try {
    new Intl.DateTimeFormat(undefined, { timeZone: candidate }).format(new Date());
    return true;
  } catch {
    return false;
  }
};

export const detectDeviceTimezone = (fallback = DEFAULT_TIMEZONE) => {
  try {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    return isValidTimezone(tz) ? tz : fallback;
  } catch {
    return fallback;
  }
};

const FALLBACK_TIMEZONES = new Set([
  'UTC',
  'ETC/UTC',
  'ETC/UCT',
  'ETC/UNIVERSAL',
  'ETC/ZULU',
  'ETC/GMT',
  'ETC/GMT+0',
  'ETC/GMT-0',
  'ETC/GREENWICH',
  'GMT',
  'UCT',
  'UNIVERSAL',
  'ZULU',
]);

const isFallbackTimezone = (tz) => {
  const candidate = ensureString(tz);
  if (!candidate) return false;
  return FALLBACK_TIMEZONES.has(candidate.trim().toUpperCase());
};

export const resolveUserTimezone = (...candidates) => {
  let fallbackTimezone = null;
  for (const candidate of candidates) {
    // Handle special "device" value by detecting device timezone
    if (candidate === 'device') {
      return detectDeviceTimezone(DEFAULT_TIMEZONE);
    }
    if (!isValidTimezone(candidate)) continue;
    const trimmed = candidate.trim();
    if (isFallbackTimezone(trimmed)) {
      if (!fallbackTimezone) fallbackTimezone = trimmed;
      continue;
    }
    return trimmed;
  }
  return fallbackTimezone || DEFAULT_TIMEZONE;
};

export const ensureDate = (value) => {
  if (!value) return null;
  if (value instanceof Date) {
    const time = value.getTime();
    return Number.isNaN(time) ? null : new Date(time);
  }
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d;
};

export const formatInTimezone = (value, options = {}, ...timezoneCandidates) => {
  const date = ensureDate(value);
  if (!date) return '';
  const tz = resolveUserTimezone(...timezoneCandidates);
  try {
    return new Intl.DateTimeFormat(undefined, { ...options, timeZone: tz }).format(date);
  } catch {
    try {
      return date.toLocaleString(undefined, options);
    } catch {
      return date.toISOString();
    }
  }
};

export const formatToPartsInTimezone = (value, options = {}, ...timezoneCandidates) => {
  const date = ensureDate(value);
  if (!date) return null;
  const tz = resolveUserTimezone(...timezoneCandidates);
  try {
    return new Intl.DateTimeFormat(undefined, { ...options, timeZone: tz }).formatToParts(date);
  } catch {
    return null;
  }
};

export const getDefaultTimezone = () => DEFAULT_TIMEZONE;
