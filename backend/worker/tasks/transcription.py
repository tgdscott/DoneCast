"""Celery task definitions related to media transcription."""

from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path

from .app import celery_app
from api.core.paths import WS_ROOT as PROJECT_ROOT
from api.services import transcription as trans


_TRANSCRIPTION_FORCE_VALUES = {"1", "true", "yes", "on"}


def _should_enable_flag(env_var: str) -> bool:
    value = os.getenv(env_var, "").strip().lower()
    return value in _TRANSCRIPTION_FORCE_VALUES


def _ensure_transcript_dir() -> Path:
    transcripts_dir = PROJECT_ROOT / "transcripts"
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    return transcripts_dir


def _write_json(path: Path, payload: object) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False)


@celery_app.task(name="transcribe_media_file")
def transcribe_media_file(filename: str) -> dict:
    """Generate transcript JSON artifacts for a media file."""

    try:
        transcripts_dir = _ensure_transcript_dir()
        force_refresh = _should_enable_flag("TRANSCRIPTION_FORCE")
        mirror_legacy = _should_enable_flag("TRANSCRIPTS_LEGACY_MIRROR")

        words = trans.get_word_timestamps(filename)
        stem = Path(filename).stem

        orig_new = transcripts_dir / f"{stem}.original.json"
        work_new = transcripts_dir / f"{stem}.json"
        orig_legacy = transcripts_dir / f"{stem}.original.words.json"
        work_legacy = transcripts_dir / f"{stem}.words.json"

        if force_refresh or (not orig_new.exists() and not orig_legacy.exists()):
            _write_json(orig_new, words)
        if force_refresh or (not work_new.exists() and not work_legacy.exists()):
            _write_json(work_new, words)

        if mirror_legacy:
            try:
                if orig_legacy.exists() and not orig_new.exists():
                    shutil.copyfile(orig_legacy, orig_new)
                if orig_new.exists() and not orig_legacy.exists():
                    shutil.copyfile(orig_new, orig_legacy)
                if work_legacy.exists() and not work_new.exists():
                    shutil.copyfile(work_legacy, work_new)
                if work_new.exists() and not work_legacy.exists():
                    shutil.copyfile(work_new, work_legacy)
            except Exception:
                logging.warning(
                    "[transcribe] Failed to mirror transcript files to legacy/new names",
                    exc_info=True,
                )

        log_template = (
            "[transcribe] FORCED fresh transcripts for %s -> %s, %s"
            if force_refresh
            else "[transcribe] cached transcripts for %s -> %s, %s"
        )
        logging.info(
            log_template,
            filename,
            orig_new.name,
            work_new.name,
        )
        if mirror_legacy:
            logging.info(
                "[transcribe] mirrored transcripts to legacy names -> %s, %s",
                orig_legacy.name,
                work_legacy.name,
            )

        return {
            "ok": True,
            "filename": filename,
            "original": orig_new.name,
            "working": work_new.name,
        }
    except Exception as exc:  # pragma: no cover - defensive logging
        logging.warning("[transcribe] failed for %s: %s", filename, exc, exc_info=True)

        try:
            if _should_enable_flag("TRANSCRIPTION_FAKE"):
                from pydub import AudioSegment as _AudioSegment  # lazy import

                source = PROJECT_ROOT / "media_uploads" / filename
                if source.is_file():
                    audio = _AudioSegment.from_file(source)
                else:
                    audio = _AudioSegment.silent(duration=10_000)

                duration_s = max(1.0, len(audio) / 1000.0)
                words = []
                current = 0.0
                index = 0
                while current < duration_s:
                    token = "flubber" if index % 10 == 5 else f"w{index}"
                    words.append(
                        {
                            "word": token,
                            "start": round(current, 3),
                            "end": round(current + 0.3, 3),
                            "speaker": None,
                        }
                    )
                    current += 0.5
                    index += 1

                transcripts_dir = _ensure_transcript_dir()
                orig_new = transcripts_dir / f"{Path(filename).stem}.original.json"
                work_new = transcripts_dir / f"{Path(filename).stem}.json"
                orig_legacy = transcripts_dir / f"{Path(filename).stem}.original.words.json"
                work_legacy = transcripts_dir / f"{Path(filename).stem}.words.json"

                if not orig_new.exists() and not orig_legacy.exists():
                    _write_json(orig_new, words)
                if not work_new.exists() and not work_legacy.exists():
                    _write_json(work_new, words)

                if _should_enable_flag("TRANSCRIPTS_LEGACY_MIRROR"):
                    try:
                        if orig_new.exists() and not orig_legacy.exists():
                            shutil.copyfile(orig_new, orig_legacy)
                        if work_new.exists() and not work_legacy.exists():
                            shutil.copyfile(work_new, work_legacy)
                    except Exception:
                        logging.warning(
                            "[transcribe] Failed to mirror fake transcripts", exc_info=True
                        )

                logging.info(
                    "[transcribe] DEV FAKE wrote %s, %s",
                    orig_new.name,
                    work_new.name,
                )
                return {
                    "ok": True,
                    "filename": filename,
                    "original": orig_new.name,
                    "working": work_new.name,
                    "fake": True,
                }
        except Exception as fallback_exc:  # pragma: no cover - defensive logging
            logging.warning(
                "[transcribe] dev-fake fallback failed: %s",
                fallback_exc,
                exc_info=True,
            )

        return {"ok": False, "filename": filename, "error": str(exc)}

