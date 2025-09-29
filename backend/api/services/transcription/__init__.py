from __future__ import annotations

"""Compatibility shim for transcription service.

This package name shadows the legacy module ``api.services.transcription``. Some
code imports the package (``from api.services import transcription``) while
others import specific modules such as
``api.services.transcription.assemblyai_client``. This module keeps both styles
working by providing the original helper functions and exporting the nested
modules.
"""

from pathlib import Path
from typing import Any, Dict, List
import json
import logging
import os

from ...core.paths import MEDIA_DIR, TRANSCRIPTS_DIR
from ..transcription_assemblyai import assemblyai_transcribe_with_speakers
from ..transcription_google import google_transcribe_with_words


class TranscriptionError(Exception):
    """Generic transcription failure."""


def get_word_timestamps(filename: str) -> List[Dict[str, Any]]:
    """Return per-word timestamps for an uploaded media file.

    Strategy:
      1. AssemblyAI with speakers (preferred)
      2. Google Speech word offsets (adds ``speaker=None``)

    Raises on failure to keep callers' error handling consistent.
    """

    audio_path = MEDIA_DIR / filename
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {filename}")

    try:
        logging.info("[transcription/pkg] Using AssemblyAI with disfluencies=True")
        return assemblyai_transcribe_with_speakers(filename)
    except Exception:
        logging.warning("[transcription/pkg] AssemblyAI failed; falling back to Google", exc_info=True)

    try:
        words = google_transcribe_with_words(filename)
        for w in words:
            if "speaker" not in w:
                w["speaker"] = None
        return words
    except Exception:
        logging.warning("[transcription/pkg] Google fallback failed", exc_info=True)
        raise NotImplementedError("Only AssemblyAI and Google transcription are supported.")


def _is_gcs_path(path: str) -> bool:
    return isinstance(path, str) and path.startswith("gs://")


def _download_gcs_to_media(gcs_uri: str) -> str:
    """Download ``gs://bucket/key`` to ``MEDIA_DIR`` and return the local filename."""

    from google.cloud import storage  # type: ignore - optional dependency in tests

    without_scheme = gcs_uri[len("gs://") :]
    bucket_name, key = without_scheme.split("/", 1)
    dst_name = os.path.basename(key) or "audio"
    dst_path = MEDIA_DIR / dst_name
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(key)
    blob.download_to_filename(str(dst_path))
    return dst_name


def transcribe_media_file(filename: str) -> List[Dict[str, Any]]:
    """Synchronously transcribe a media file and persist transcript artifacts."""

    local_name = filename
    delete_after = False
    if _is_gcs_path(filename):
        try:
            local_name = _download_gcs_to_media(filename)
            delete_after = True
        except Exception as exc:  # pragma: no cover - network dependent
            logging.error("[transcription] GCS download failed for %s: %s", filename, exc)
            raise

    try:
        words = get_word_timestamps(local_name)
        try:
            TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
            stem = Path(local_name).stem
            out_path = TRANSCRIPTS_DIR / f"{stem}.json"
            if not out_path.exists():
                payload = json.dumps(words, ensure_ascii=False, indent=2)
                out_path.write_text(payload, encoding="utf-8")
                try:
                    bucket = (os.getenv("TRANSCRIPTS_BUCKET") or os.getenv("MEDIA_BUCKET") or "").strip()
                    if bucket:
                        from ...infrastructure.gcs import upload_bytes  # type: ignore

                        upload_bytes(
                            bucket,
                            f"transcripts/{stem}.json",
                            payload.encode("utf-8"),
                            content_type="application/json; charset=utf-8",
                        )
                except Exception:  # pragma: no cover - GCS optional
                    pass
        except Exception:  # pragma: no cover - best effort persistence
            pass
        return words
    finally:
        if delete_after:
            try:
                (MEDIA_DIR / local_name).unlink(missing_ok=True)
            except Exception:
                pass


# Re-export frequently used helper modules for compatibility with legacy imports
from . import assemblyai_client  # noqa: E402  # isort: skip
from . import transcription_runner  # noqa: E402  # isort: skip


__all__ = [
    "TranscriptionError",
    "get_word_timestamps",
    "transcribe_media_file",
    "assemblyai_client",
    "transcription_runner",
]

