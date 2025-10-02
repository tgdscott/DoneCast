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
from .watchers import notify_watchers_processed, mark_watchers_failed


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

    # Prefer AssemblyAI. Import lazily to avoid optional deps during package import.
    try:
        from ..transcription_assemblyai import assemblyai_transcribe_with_speakers  # local import
        logging.info("[transcription/pkg] Using AssemblyAI with disfluencies=True")
        return assemblyai_transcribe_with_speakers(filename)
    except Exception:
        logging.warning("[transcription/pkg] AssemblyAI failed; falling back to Google", exc_info=True)

    try:
        # Lazy import to avoid ImportError if google-cloud-speech isn't installed in test envs
        from ..transcription_google import google_transcribe_with_words  # local import
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

    try:
        from google.cloud import storage  # type: ignore - optional dependency in tests
    except Exception as exc:  # pragma: no cover - optional dependency missing in tests
        raise RuntimeError("google-cloud-storage not installed") from exc

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


def _read_existing_transcript_for(filename: str) -> List[Dict[str, Any]] | None:
    """Return transcript words if an existing JSON is present for filename.

    Checks TRANSCRIPTS_DIR and a workspace-level transcripts folder for common
    variants, reusing existing artifacts to avoid re-transcription.
    """
    try:
        stem = Path(filename).stem
    except Exception:
        stem = Path(str(filename)).stem

    candidates = [
        TRANSCRIPTS_DIR / f"{stem}.json",
        TRANSCRIPTS_DIR / f"{stem}.words.json",
    ]
    # Workspace-level transcripts directory
    try:
        ws_root = MEDIA_DIR.parent  # WS_ROOT
        ws_tr = ws_root / "transcripts"
        candidates.extend([ws_tr / f"{stem}.json", ws_tr / f"{stem}.words.json"])
    except Exception:
        pass

    for path in candidates:
        try:
            if path.is_file():
                data = path.read_text(encoding="utf-8")
                return json.loads(data)
        except Exception:
            continue
    return None


def transcribe_media_file(filename: str) -> List[Dict[str, Any]]:

    """Synchronously transcribe a media file and persist transcript artifacts."""

    # Global safeguard: allow disabling brand-new transcription at runtime.
    raw_toggle = os.getenv("ALLOW_TRANSCRIPTION") or os.getenv("TRANSCRIBE_ENABLED")

    # First, if we already have a transcript JSON, reuse it and return early.
    existing = _read_existing_transcript_for(filename)
    if existing is not None:
        logging.info("[transcription] Reusing existing transcript for %s", filename)
        notify_watchers_processed(filename)
        return existing

    local_name = filename
    delete_after = False
    try:
        if _is_gcs_path(filename):
            try:
                local_name = _download_gcs_to_media(filename)
                delete_after = True
            except Exception as exc:  # pragma: no cover - network dependent
                logging.error("[transcription] GCS download failed for %s: %s", filename, exc)
                raise

        # Respect global kill-switch if set to falsey values.
        if raw_toggle and str(raw_toggle).strip().lower() in {"0", "false", "no", "off"}:
            raise TranscriptionError("Transcription disabled by environment")

        words = get_word_timestamps(local_name)
        try:
            TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
            stem = Path(local_name).stem
            out_path = TRANSCRIPTS_DIR / f"{stem}.json"
            if not out_path.exists():
                payload = json.dumps(words, ensure_ascii=False, indent=2)
                out_path.write_text(payload, encoding="utf-8")
                gcs_url = None
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
                        gcs_url = f"https://storage.googleapis.com/{bucket}/transcripts/{stem}.json"
                except Exception:  # pragma: no cover - GCS optional
                    pass
                # Associate transcript with episode
                try:
                    from api.services.episodes.repo import get_episode_by_id, update_episode
                    from uuid import UUID
                    # Try to extract episode_id from stem (assumes stem is episode UUID or contains it)
                    episode_id = None
                    try:
                        episode_id = UUID(stem)
                    except Exception:
                        pass
                    if episode_id:
                        from api.core.database import get_session
                        session_gen = get_session()
                        session = next(session_gen)
                        ep = get_episode_by_id(session, episode_id)
                        if ep:
                            meta = json.loads(ep.meta_json or "{}")
                            transcripts = meta.get("transcripts", {})
                            transcripts["gcs_json"] = gcs_url
                            meta["transcripts"] = transcripts
                            ep.meta_json = json.dumps(meta)
                            update_episode(session, ep, {"meta_json": ep.meta_json})
                except Exception as e:
                    logging.warning(f"Failed to associate transcript with episode: {e}")
        except Exception:  # pragma: no cover - best effort persistence
            pass

        notify_watchers_processed(filename)
        return words
    except Exception as exc:
        mark_watchers_failed(filename, str(exc))
        raise
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

