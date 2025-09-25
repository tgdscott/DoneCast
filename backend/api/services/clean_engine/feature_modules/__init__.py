from __future__ import annotations

# Re-export grouped feature functions to preserve original public API

# FFmpeg bootstrap
from .ffmpeg_bootstrap import ensure_ffmpeg

# Utilities
from .utils import to_ms, slice_ms, detect_silences_dbfs, find_phrase

# Flubber
from .flubber import prepare_flubber_contexts, apply_flubber_cuts

# Intern
from .intern import insert_intern_responses

# Fillers
from .fillers import remove_fillers

# Pauses
from .pauses import compress_dead_air_middle

# Profanity censor
from .censor import apply_censor_beep

# SFX replacement
from .sfx import replace_keywords_with_sfx

__all__ = [
    # FFmpeg
    "ensure_ffmpeg",
    # Utils
    "to_ms", "slice_ms", "detect_silences_dbfs", "find_phrase",
    # Flubber
    "prepare_flubber_contexts", "apply_flubber_cuts",
    # Intern
    "insert_intern_responses",
    # Fillers
    "remove_fillers",
    # Pauses
    "compress_dead_air_middle",
    # Censor
    "apply_censor_beep",
    # SFX
    "replace_keywords_with_sfx",
]
