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
  { level: 1, ratio: 0.1, description: "Barely audible under the host" },
  { level: 2, ratio: 0.2, description: "Very soft background bed" },
  { level: 3, ratio: 0.3, description: "Gentle supporting layer" },
  { level: 4, ratio: 0.4, description: "Noticeable but still tucked under" },
  { level: 5, ratio: 0.5, description: "Balanced bed under the voice" },
  { level: 6, ratio: 0.6, description: "Present with a mild punch" },
  { level: 7, ratio: 0.7, description: "Energetic mix that rides with the host" },
  { level: 8, ratio: 0.8, description: "Almost level with the dialogue" },
  { level: 9, ratio: 0.9, description: "Bold mix that demands attention" },
  { level: 10, ratio: 1.0, description: "Same volume as the main mix" },
  { level: 11, ratio: MUSIC_VOLUME_BOOST_RATIO, description: "Spinal Tap mode – louder than the main mix" },
];

export const DEFAULT_VOLUME_LEVEL = 4;

export const volumeLevelToDb = (level) => {
  if (typeof level !== "number" || Number.isNaN(level)) level = DEFAULT_VOLUME_LEVEL;
  const clamped = Math.max(1, Math.min(11, level));
  let ratio;
  if (clamped <= 10) {
    // Level directly represents percentage: 8.2 = 82% of voice volume
    ratio = clamped / 10;
  } else {
    // Above 10, boost beyond voice level
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
  if (ratio <= 1) {
    return Math.max(1, Math.min(10, ratio * 10));
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
