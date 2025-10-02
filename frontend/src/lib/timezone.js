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

export const resolveUserTimezone = (...candidates) => {
  for (const candidate of candidates) {
    if (isValidTimezone(candidate)) {
      return candidate.trim();
    }
  }
  return DEFAULT_TIMEZONE;
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
