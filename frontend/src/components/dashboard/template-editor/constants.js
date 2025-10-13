// Icon color mappings for segment and source types
export const segmentIconColors = {
  intro: "text-blue-500",
  outro: "text-purple-500",
  content: "text-green-500",
  commercial: "text-orange-500",
};

export const sourceIconColors = {
  static: "text-gray-500",
  tts: "text-orange-500",
};
import { FileText, Mic, Music } from "lucide-react";

export const AI_DEFAULT = {
  auto_fill_ai: true,
  title_instructions: "",
  notes_instructions: "",
  tags_instructions: "",
  tags_always_include: [],
  auto_generate_tags: true,
};

export const MUSIC_VOLUME_BOOST_RATIO = 1.35;

export const MUSIC_VOLUME_LEVELS = [
  { level: 1, ratio: 0.4, description: "Soft background bed" },
  { level: 2, ratio: 0.5, description: "Gentle supporting layer" },
  { level: 3, ratio: 0.6, description: "Noticeable and present" },
  { level: 4, ratio: 0.7, description: "Balanced bed under the voice" },
  { level: 5, ratio: 0.8, description: "Energetic with punch" },
  { level: 6, ratio: 0.9, description: "Strong presence riding with the host" },
  { level: 7, ratio: 1.0, description: "Same volume as the main mix" },
  { level: 8, ratio: 1.1, description: "Slightly above dialogue level" },
  { level: 9, ratio: 1.2, description: "Bold and prominent" },
  { level: 10, ratio: 1.3, description: "Music-forward mix" },
  { level: 11, ratio: MUSIC_VOLUME_BOOST_RATIO, description: "Spinal Tap mode – maximum loudness" },
];

export const DEFAULT_VOLUME_LEVEL = 4;

export const volumeLevelToDb = (level) => {
  if (typeof level !== "number" || Number.isNaN(level)) level = DEFAULT_VOLUME_LEVEL;
  const clamped = Math.max(1, Math.min(11, level));
  let ratio;
  if (clamped <= 10) {
    // Shifted mapping: level 6.8 should give 98% (what 9.8 used to give)
    // This means we add 3.0 to the level before converting to ratio
    // New formula: ratio = (level + 3) / 10
    const adjustedLevel = clamped + 3.0;
    ratio = adjustedLevel / 10;
    // Ensure ratio doesn't exceed 1.3 (before going to level 11 territory)
    ratio = Math.min(ratio, 1.3);
  } else {
    // Above 10, boost beyond voice level (Spinal Tap mode)
    const extra = MUSIC_VOLUME_BOOST_RATIO - 1;
    ratio = 1 + (clamped - 10) * (extra <= 0 ? 0 : extra);
  }
  if (ratio <= 0) return -60;
  return 20 * Math.log10(ratio);
};

export const volumeDbToLevel = (db) => {
  if (typeof db !== "number" || Number.isNaN(db)) return DEFAULT_VOLUME_LEVEL;
  const ratio = Math.pow(10, db / 20);
  if (!Number.isFinite(ratio) || ratio <= 0) return DEFAULT_VOLUME_LEVEL;
  if (ratio <= 1.3) {
    // Inverse of the shifted mapping: level = (ratio * 10) - 3
    const level = (ratio * 10) - 3.0;
    return Math.max(1, Math.min(10, level));
  }
  const extra = MUSIC_VOLUME_BOOST_RATIO - 1;
  if (extra <= 0) return 11;
  const level = 10 + (ratio - 1) / extra;
  return Math.max(10, Math.min(11, level));
};

export const describeVolumeLevel = (level) => {
  const rounded = Math.round(level);
  const preset = MUSIC_VOLUME_LEVELS.find((item) => item.level === rounded);
  return preset ? preset.description : "";
};

export const segmentIcons = {
  intro: Music,
  outro: Music,
  content: FileText,
  commercial: Mic,
};

export const sourceIcons = {
  static: FileText,
  tts: Mic,
};
