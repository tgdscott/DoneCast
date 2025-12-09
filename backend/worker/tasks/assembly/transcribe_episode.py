from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from sqlmodel import Session, select

from api.core.paths import TRANSCRIPTS_DIR
from api.core.config import settings
from api.models.transcription import TranscriptionWatch
from api.models.user import User
from api.services.audio.common import sanitize_filename
from api.services.transcription.transcription_runner import run_assemblyai_job
from api.services.transcription.assemblyai_client import AssemblyAITranscriptionError
from api.services.transcription.watchers import notify_watchers_processed, mark_watchers_failed, _candidate_filenames
from api.services.transcription import _store_media_transcript_metadata, _resolve_transcripts_bucket

from infrastructure import storage  # type: ignore

logger = logging.getLogger("assembly.transcribe")


def _touch_watch_status(session: Session, filename: str, status: str) -> None:
    """Update any outstanding watch rows to reflect current status."""

    candidates = _candidate_filenames(filename)
    if filename not in candidates:
        candidates.insert(0, filename)

    watches = session.exec(
        select(TranscriptionWatch).where(
            TranscriptionWatch.filename.in_(candidates),  # type: ignore[arg-type]
            TranscriptionWatch.notified_at == None,  # noqa: E711
        )
    ).all()

    for watch in watches:
        watch.last_status = status
        session.add(watch)

    if watches:
        session.commit()


def _resolve_audio_path(media_context) -> Path:
    """Return the local path to the audio file we need to transcribe."""

    candidate = getattr(media_context, "source_audio_path", None)
    if candidate and isinstance(candidate, Path):
        if candidate.exists():
            return candidate
    if candidate:
        # `source_audio_path` might be a string
        try:
            path_obj = Path(str(candidate))
            if path_obj.exists():
                return path_obj
        except Exception:
            pass
    raise FileNotFoundError("Source audio not found for transcription")


def _build_runner_config(*, timeout_s: float | int | None = None) -> Dict[str, Any]:
    api_key = settings.ASSEMBLYAI_API_KEY
    if not api_key or api_key == "YOUR_API_KEY_HERE":
        raise AssemblyAITranscriptionError("AssemblyAI API key not configured")

    webhook_cfg: Dict[str, Any] = {}
    webhook_secret = getattr(settings, "ASSEMBLYAI_WEBHOOK_SECRET", None)
    webhook_url = getattr(settings, "ASSEMBLYAI_WEBHOOK_URL", None)
    if webhook_secret:
        resolved_url: Optional[str] = None
        if webhook_url:
            resolved_url = webhook_url.rstrip("/")
        else:
            base = (settings.APP_BASE_URL or "").strip()
            if base:
                resolved_url = f"{base.rstrip('/')}/api/assemblyai/webhook"
        if resolved_url:
            header_name = (getattr(settings, "ASSEMBLYAI_WEBHOOK_HEADER", None) or "X-AssemblyAI-Signature").strip() or "X-AssemblyAI-Signature"
            webhook_cfg = {
                "url": resolved_url,
                "secret": webhook_secret,
                "auth_header_name": header_name,
            }

    cfg: Dict[str, Any] = {
        "api_key": api_key,
        "base_url": "https://api.assemblyai.com/v2",
        "params": {
            "language_code": "en_us",
            "speaker_labels": True,
            "punctuate": True,
            "format_text": False,
            "disfluencies": True,  # Keep fillers; cleanup happens downstream
            "filter_profanity": False,
            "language_detection": False,
            "custom_spelling": [],
            "multichannel": False,
        },
        "polling": {
            "interval_s": 1.0,
            "max_interval_s": 8.0,
            "backoff": 1.5,
            "timeout_s": float(timeout_s or 7200),
        },
    }

    if webhook_cfg:
        cfg["webhook"] = webhook_cfg

    return cfg


def _persist_transcript(words: list[dict[str, Any]], *, stem: str, original_filename: str) -> Path:
    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = TRANSCRIPTS_DIR / f"{stem}.json"
    payload = json.dumps(words, ensure_ascii=False)
    out_path.write_text(payload, encoding="utf-8")

    # Upload to GCS (never fall back to local-only) so transcripts survive container restarts
    gcs_uri: str | None = None
    gcs_url: str | None = None
    bucket: str | None = None
    key: str | None = None
    try:
        bucket = _resolve_transcripts_bucket()
        safe_stem = sanitize_filename(stem) or stem
        key = f"transcripts/{safe_stem}.json"
        storage_url = storage.upload_bytes(  # type: ignore[attr-defined]
            bucket,
            key,
            payload.encode("utf-8"),
            content_type="application/json; charset=utf-8",
        )
        if storage_url:
            if storage_url.startswith("gs://"):
                gcs_uri = storage_url
                gcs_url = f"https://storage.googleapis.com/{bucket}/{key}"
            else:
                # Transcripts must live in GCS; construct deterministic URIs even if backend misconfigured
                logger.error(
                    "[transcribe] Non-GCS storage URL returned for transcript: %s", storage_url
                )
                gcs_uri = f"gs://{bucket}/{key}"
                gcs_url = f"https://storage.googleapis.com/{bucket}/{key}"
    except Exception as upload_err:
        logger.error(
            "[transcribe] ❌ Failed to upload transcript to GCS: %s", upload_err, exc_info=True
        )
        raise

    try:
        _store_media_transcript_metadata(
            original_filename,
            stem=stem,
            safe_stem=safe_stem,
            bucket=bucket,
            key=key,
            gcs_uri=gcs_uri,
            gcs_url=gcs_url,
        )
    except Exception as meta_err:
        logger.warning("[transcribe] Failed to store transcript metadata: %s", meta_err, exc_info=True)
    return out_path


def transcribe_episode(
    *,
    session: Session,
    episode,
    user: User,
    podcast,
    media_context,
    main_content_filename: str,
    output_filename: str,
    tts_values: dict,
    episode_details: dict,
) -> Dict[str, Any]:
    """Submit AssemblyAI job, poll, and return words_json_path for orchestrator.

    Returns a dict with ``words_json_path`` pointing to the saved transcript JSON.
    Raises on failure so orchestrator can surface the error upstream.
    """

    audio_path = _resolve_audio_path(media_context)
    logger.info("[transcribe] 🚀 Starting AssemblyAI job for %s", audio_path.name)

    # Mark watchers as processing
    try:
        _touch_watch_status(session, main_content_filename, "processing")
    except Exception:
        logger.warning("[transcribe] Failed to update watcher status to processing", exc_info=True)

    cfg = _build_runner_config()
    log_lines: list[str] = []

    try:
        result = run_assemblyai_job(audio_path, cfg, log_lines)  # type: ignore[arg-type]
        words = list(result.get("words") or [])
        if not words:
            raise AssemblyAITranscriptionError("AssemblyAI returned no words")
    except Exception as exc:
        detail = str(exc)
        logger.error("[transcribe] ❌ AssemblyAI transcription failed: %s", detail, exc_info=True)
        try:
            _touch_watch_status(session, main_content_filename, f"error:{detail[:120]}")
            mark_watchers_failed(main_content_filename, detail)
        except Exception:
            logger.warning("[transcribe] Failed to mark watchers failed", exc_info=True)
        raise

    # Persist transcript locally and in metadata
    try:
        stem = Path(output_filename or main_content_filename).stem
    except Exception:
        stem = Path(main_content_filename).stem

    out_path = _persist_transcript(words, stem=stem, original_filename=main_content_filename)
    logger.info("[transcribe] ✅ Transcript saved to %s (%d words)", out_path, len(words))

    try:
        notify_watchers_processed(main_content_filename)
    except Exception:
        logger.warning("[transcribe] Failed to notify watchers", exc_info=True)

    return {"words_json_path": out_path}
