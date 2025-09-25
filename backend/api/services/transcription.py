import os
import io
import logging
from pathlib import Path
from typing import List, Dict, Any
from pydub import AudioSegment

from ..core.config import settings
from api.core.paths import MEDIA_DIR
from .transcription_assemblyai import assemblyai_transcribe_with_speakers, AssemblyAITranscriptionError
from .transcription_google import google_transcribe_with_words, GoogleTranscriptionError


# UPLOAD_DIR = Path("temp_uploads") # Removed, using MEDIA_DIR

# OpenAI Whisper API has a 25MB file size limit. To handle larger files,
# we will chunk the audio into 10-minute segments, as a 10-minute MP3
# will reliably be under the 25MB limit.
CHUNK_DURATION_MS = 10 * 60 * 1000

class TranscriptionError(Exception):
    """Custom exception for transcription failures."""
    pass

def get_word_timestamps(filename: str) -> List[Dict[str, Any]]:
    """Multi-provider transcription with diarization priority.

    Order:
      1. AssemblyAI (speaker diarization: returns speaker labels)
      2. Google Speech (word offsets only)
      3. OpenAI Whisper (word offsets only)

    Returns list of dicts: { word, start, end, speaker? }
    """
    audio_path = MEDIA_DIR / filename  # Use MEDIA_DIR here
    if not audio_path.exists():
        raise TranscriptionError(f"Audio file not found: {filename}")

    # 1. AssemblyAI
    try:
        logging.info("[transcription] Using AssemblyAI with disfluencies=True, filter_profanity=False")
        return assemblyai_transcribe_with_speakers(filename)
    except Exception:
        logging.warning("[transcription] AssemblyAI failed; falling back to Google", exc_info=True)

    # 2. Google
    try:
        words = google_transcribe_with_words(filename)
        # ensure schema compatibility
        for w in words:
            if 'speaker' not in w:
                w['speaker'] = None
        return words
    except Exception:
        logging.warning("[transcription] Google fallback failed", exc_info=True)

    # 3. Whisper fallback removed. Only AssemblyAI and Google are supported.
    raise NotImplementedError("Only AssemblyAI and Google transcription are supported.")
