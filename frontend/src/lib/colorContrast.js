// Color contrast utilities for readability checks (WCAG-inspired)
// Implements the user's specified guidelines.

function clamp01(x) {
  return Math.min(1, Math.max(0, x));
}

// Convert hex (#RRGGBB or #RGB) to { r, g, b } 0-255
export function hexToRgb(hex) {
  if (!hex) return null;
  let h = hex.trim();
  if (h.startsWith('#')) h = h.slice(1);
  if (h.length === 3) {
    h = h.split('').map((c) => c + c).join('');
  }
  if (h.length !== 6) return null;
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  if ([r, g, b].some((v) => Number.isNaN(v))) return null;
  return { r, g, b };
}

// Relative luminance using sRGB to linear conversion and coefficients.
// Note: The prompt specifies L = 0.2126*R + 0.7152*G + 0.0722*B with normalized R,G,B.
// For better accuracy, we convert sRGB to linear per WCAG.
function srgbToLinear(c) {
  const cs = c / 255;
  if (cs <= 0.03928) return cs / 12.92;
  return Math.pow((cs + 0.055) / 1.055, 2.4);
}

export function relativeLuminanceFromRgb({ r, g, b }) {
  const R = srgbToLinear(r);
  const G = srgbToLinear(g);
  const B = srgbToLinear(b);
  return clamp01(0.2126 * R + 0.7152 * G + 0.0722 * B);
}

export function relativeLuminanceFromHex(hex) {
  const rgb = hexToRgb(hex);
  if (!rgb) return null;
  return relativeLuminanceFromRgb(rgb);
}

// Contrast ratio (L1 + 0.05) / (L2 + 0.05) with L1 >= L2
export function contrastRatio(l1, l2) {
  const L1 = Math.max(l1, l2);
  const L2 = Math.min(l1, l2);
  return (L1 + 0.05) / (L2 + 0.05);
}

export function contrastRatioHex(fgHex, bgHex) {
  const lf = relativeLuminanceFromHex(fgHex);
  const lb = relativeLuminanceFromHex(bgHex);
  if (lf == null || lb == null) return null;
  return contrastRatio(lf, lb);
}

// Check readability against threshold (default 4.5:1 for normal text)
export function isReadable(fgHex, bgHex, threshold = 4.5) {
  const ratio = contrastRatioHex(fgHex, bgHex);
  if (ratio == null) return false;
  return ratio >= threshold;
}

// Simplified black/white selection based on brightness midpoint.
// Brightness here uses simple average or perceived brightness.
// We'll use perceived brightness: 0.299R + 0.587G + 0.114B
export function chooseTextColorBW(bgHex, midpoint = 128) {
  const rgb = hexToRgb(bgHex);
  if (!rgb) return null;
  const brightness = 0.299 * rgb.r + 0.587 * rgb.g + 0.114 * rgb.b;
  return brightness < midpoint ? '#FFFFFF' : '#000000';
}

// Suggest a better text color when unreadable: tries black or white and picks better contrast.
export function suggestTextColor(fgHex, bgHex) {
  const ratio = contrastRatioHex(fgHex, bgHex);
  if (ratio == null) return null;
  if (ratio >= 4.5) return fgHex; // already readable
  const blackRatio = contrastRatioHex('#000000', bgHex) ?? 0;
  const whiteRatio = contrastRatioHex('#FFFFFF', bgHex) ?? 0;
  return blackRatio >= whiteRatio ? '#000000' : '#FFFFFF';
}

// Optional: choose black/white but ensure >= 4.5 if possible
export function chooseReadableBW(bgHex, threshold = 4.5) {
  const bw = chooseTextColorBW(bgHex);
  if (!bw) return null;
  const r = contrastRatioHex(bw, bgHex);
  if (r == null) return bw;
  if (r >= threshold) return bw;
  // If midpoint suggestion fails threshold, pick the better of black/white
  const blackRatio = contrastRatioHex('#000000', bgHex) ?? 0;
  const whiteRatio = contrastRatioHex('#FFFFFF', bgHex) ?? 0;
  return blackRatio >= whiteRatio ? '#000000' : '#FFFFFF';
}

export default {
  hexToRgb,
  relativeLuminanceFromRgb,
  relativeLuminanceFromHex,
  contrastRatio,
  contrastRatioHex,
  isReadable,
  chooseTextColorBW,
  suggestTextColor,
  chooseReadableBW,
};
