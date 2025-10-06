/**
 * Format bytes to human-readable size (B, KB, MB, GB)
 */
export const formatBytes = (bytes) => {
  if (!Number.isFinite(bytes) || bytes <= 0) return '';
  const units = ['B', 'KB', 'MB', 'GB'];
  let value = bytes;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i++;
  }
  return `${value.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
};

/**
 * Format bytes per second to human-readable speed
 */
export const formatSpeed = (bytesPerSecond) => {
  if (!Number.isFinite(bytesPerSecond) || bytesPerSecond <= 0) return '';
  return `${formatBytes(bytesPerSecond)}/s`;
};

/**
 * Format seconds to time remaining (e.g., "2m 15s remaining")
 */
export const formatEta = (seconds) => {
  if (!Number.isFinite(seconds) || seconds <= 0) return '';
  const minutes = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  if (minutes > 0) {
    return `${minutes}m ${secs.toString().padStart(2, '0')}s remaining`;
  }
  return `${secs}s remaining`;
};

/**
 * Format full progress details (e.g., "450 MB of 1 GB • 8.5 MB/s • 2m 15s")
 */
export const formatProgressDetail = (loaded, total, speed, eta) => {
  const parts = [];
  const loadedLabel = formatBytes(loaded);
  const totalLabel = formatBytes(total);
  if (loadedLabel && totalLabel) {
    parts.push(`${loadedLabel} of ${totalLabel}`);
  } else if (loadedLabel) {
    parts.push(loadedLabel);
  }
  const speedLabel = formatSpeed(speed);
  if (speedLabel) parts.push(speedLabel);
  const etaLabel = formatEta(eta);
  if (etaLabel) parts.push(etaLabel);
  return parts.join(' • ');
};
