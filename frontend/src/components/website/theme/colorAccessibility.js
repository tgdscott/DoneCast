import { isReadable, suggestTextColor, chooseReadableBW } from "@/lib/colorContrast";

const HEX_PATTERN = /^#?(?:[0-9a-f]{3}|[0-9a-f]{6})$/i;
const CSS_VAR_PATTERN = /^var\(/i;

function isCssReference(value) {
  if (typeof value !== "string") return false;
  return CSS_VAR_PATTERN.test(value.trim());
}

export function normalizeHexColor(value) {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  if (!HEX_PATTERN.test(trimmed.startsWith("#") ? trimmed.slice(1) : trimmed)) {
    return null;
  }
  let hex = trimmed.startsWith("#") ? trimmed.slice(1) : trimmed;
  if (hex.length === 3) {
    hex = hex.split("").map((char) => char + char).join("");
  }
  if (hex.length !== 6) return null;
  return `#${hex.toUpperCase()}`;
}

export function ensureReadablePair({
  background,
  text,
  fallbackText = "#0F172A",
  threshold = 4.5,
} = {}) {
  if (isCssReference(background) || isCssReference(text)) {
    return {
      background,
      text: text || fallbackText,
      changed: !text,
      reason: "css-variable",
    };
  }

  const normalizedBg = normalizeHexColor(background);
  const normalizedFallback = normalizeHexColor(fallbackText);
  let normalizedText = normalizeHexColor(text);

  if (!normalizedBg) {
    return {
      background,
      text: text || fallbackText,
      changed: false,
      reason: "invalid-background",
    };
  }

  if (!normalizedText && normalizedFallback) {
    normalizedText = normalizedFallback;
  }

  if (!normalizedText) {
    normalizedText = chooseReadableBW(normalizedBg, threshold) || "#000000";
  }

  if (isReadable(normalizedText, normalizedBg, threshold)) {
    return {
      background: normalizedBg,
      text: normalizedText,
      changed: false,
      reason: "readable",
    };
  }

  const suggestion = normalizeHexColor(suggestTextColor(normalizedText, normalizedBg)) || normalizedText;

  return {
    background: normalizedBg,
    text: suggestion,
    changed: true,
    reason: "adjusted",
  };
}

export function ensureTextOnBackground(text, {
  background = "#FFFFFF",
  fallbackText = "#0F172A",
  threshold = 4.5,
} = {}) {
  return ensureReadablePair({
    background,
    text,
    fallbackText,
    threshold,
  }).text;
}

export default {
  normalizeHexColor,
  ensureReadablePair,
  ensureTextOnBackground,
};
