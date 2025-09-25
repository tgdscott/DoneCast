from __future__ import annotations

"""
Back-compat package that re-exports feature functions from feature_modules.

Keep imports stable:
    from api.services.clean_engine.features import ensure_ffmpeg, remove_fillers, ...

Constants live in .constants (not imported here to avoid API surface changes).
"""

from ..feature_modules import (
    ensure_ffmpeg,
    to_ms,
    slice_ms,
    detect_silences_dbfs,
    find_phrase,
    prepare_flubber_contexts,
    apply_flubber_cuts,
    insert_intern_responses,
    remove_fillers,
    compress_dead_air_middle,
    apply_censor_beep,
    replace_keywords_with_sfx,
)

__all__ = [
    "ensure_ffmpeg",
    "to_ms",
    "slice_ms",
    "detect_silences_dbfs",
    "find_phrase",
    "prepare_flubber_contexts",
    "apply_flubber_cuts",
    "insert_intern_responses",
    "remove_fillers",
    "compress_dead_air_middle",
    "apply_censor_beep",
    "replace_keywords_with_sfx",
]
