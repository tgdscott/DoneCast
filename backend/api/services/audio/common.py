from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydub import AudioSegment

# Centralized media dir import
from api.core.paths import MEDIA_DIR

# --- Constants ---
DEFAULT_TARGET_DBFS = -18.0
MAX_GAIN_DB = 9.0
MIN_RMS_THRESHOLD = 80  # treat very low RMS as silence (pydub gives huge -inf dBFS)
FILLER_LEAD_TRIM_DEFAULT_MS = 60

# --- FFmpeg/FFprobe discovery ---
_ffmpeg = os.environ.get("FFMPEG_BIN") or shutil.which("ffmpeg")
_ffprobe = os.environ.get("FFPROBE_BIN") or shutil.which("ffprobe")
if _ffmpeg:
    AudioSegment.converter = _ffmpeg  # type: ignore[attr-defined]
    AudioSegment.ffmpeg = _ffmpeg  # type: ignore[attr-defined]
if _ffprobe:
    AudioSegment.ffprobe = _ffprobe  # type: ignore[attr-defined]


# --- Small helpers ---
def match_target_dbfs(segment: AudioSegment, target_dbfs: float = DEFAULT_TARGET_DBFS) -> AudioSegment:
    """Nudge segment average dBFS toward target without extreme jumps."""
    try:
        current = segment.dBFS
    except Exception:
        return segment
    if segment.rms < MIN_RMS_THRESHOLD:
        return segment
    change_needed = target_dbfs - current
    if change_needed > MAX_GAIN_DB:
        change_needed = MAX_GAIN_DB
    if change_needed < -MAX_GAIN_DB:
        change_needed = -MAX_GAIN_DB
    return segment.apply_gain(change_needed)


def sanitize_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\s]+', '-', name).lower()


# Public re-exports
__all__ = [
    "AudioSegment",
    "MEDIA_DIR",
    "DEFAULT_TARGET_DBFS",
    "FILLER_LEAD_TRIM_DEFAULT_MS",
    "match_target_dbfs",
    "sanitize_filename",
]
