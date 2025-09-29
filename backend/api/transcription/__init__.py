from __future__ import annotations

"""
Compatibility shim for transcription service.

This package name shadows the legacy module `api.services.transcription`.
Some code imports the package (e.g., `from api.services import transcription as trans`)
and expects `get_word_timestamps` to exist. Provide a thin wrapper that mirrors
the logic from the module so both import styles work.
"""

from typing import List, Dict, Any
import logging
from pathlib import Path

from ..core.paths import MEDIA_DIR


def get_word_timestamps(filename: str) -> List[Dict[str, Any]]:
    """Return per-word timestamps for an uploaded media file.

    Strategy:
      1. AssemblyAI with speakers (preferred)
      2. Google Speech word offsets (adds speaker=None)

    Raises on failure to keep callers' error handling consistent.
    """

    audio_path = MEDIA_DIR / filename
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {filename}")

    # Prefer AssemblyAI; local import avoids module-level circular imports.
    try:
        from ..services.transcription_assemblyai import assemblyai_transcribe_with_speakers

        logging.info("[transcription/pkg] Using AssemblyAI with disfluencies=True")
        return assemblyai_transcribe_with_speakers(filename)
    except Exception:
        logging.warning("[transcription/pkg] AssemblyAI failed; falling back to Google", exc_info=True)

    # Fallback to Google Speech on failure.
    try:
        from ..services.transcription_google import google_transcribe_with_words  # type: ignore

        words = google_transcribe_with_words(filename)
        for word in words:
            if "speaker" not in word:
                word["speaker"] = None
        return words
    except Exception:
        logging.warning("[transcription/pkg] Google fallback failed", exc_info=True)
        raise NotImplementedError("Only AssemblyAI and Google transcription are supported.")
