import logging
from pathlib import Path
from typing import List, Dict, Any

from ..core.config import settings
from api.core.paths import MEDIA_DIR

from api.services.transcription.transcription_runner import run_assemblyai_job
from api.services.transcription.assemblyai_client import AssemblyAITranscriptionError as _ClientError

ASSEMBLYAI_BASE = "https://api.assemblyai.com/v2"


class AssemblyAITranscriptionError(Exception):
    pass


def assemblyai_transcribe_with_speakers(filename: str, timeout_s: int = 1800) -> List[Dict[str, Any]]:
    """
    Thin façade: build cfg from settings/env, delegate to runner, return same shape as before.
    """
    api_key = settings.ASSEMBLYAI_API_KEY
    if not api_key or api_key == "YOUR_API_KEY_HERE":
        raise AssemblyAITranscriptionError("AssemblyAI API key not configured")

    audio_path = MEDIA_DIR / filename
    if not audio_path.exists():
        raise AssemblyAITranscriptionError(f"Audio file not found: {filename}")

    cfg: Dict[str, Any] = {
        "api_key": api_key,
        "base_url": ASSEMBLYAI_BASE,
        "params": {
            # Defaults mirror monolith payload; runner/client preserve logging
            "language_code": "en_us",
            "speaker_labels": True,
            "punctuate": True,
            "format_text": False,
            "disfluencies": True,
            "filter_profanity": False,
            "language_detection": False,
            "custom_spelling": [],
            "multichannel": False,
        },
        "polling": {
            "interval_s": 5.0,
            "timeout_s": float(timeout_s or 1800),
        },
    }

    # Delegate to the runner; rewrap errors into legacy exception class to preserve type
    try:
        out = run_assemblyai_job(audio_path, cfg, log=[])
    except _ClientError as e:
        raise AssemblyAITranscriptionError(str(e))

    # Runner returns {"words": [...]}; legacy returned just the list
    words = list(out.get("words") or [])
    return words
