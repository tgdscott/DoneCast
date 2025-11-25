"""Celery task entry-point for media transcription."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

from .app import celery_app
from api.core.paths import TRANSCRIPTS_DIR, MEDIA_DIR
from api.services.transcription import transcribe_media_file as run_transcription
from api.services.transcription.watchers import notify_watchers_processed


@celery_app.task(name="transcribe_media_file")
def transcribe_media_file(filename: str, user_id: str | None = None, guest_ids: list[str] | None = None) -> dict:
    """Generate transcript artifacts for the uploaded media file."""

    try:
        tr_dir = TRANSCRIPTS_DIR
        tr_dir.mkdir(parents=True, exist_ok=True)

        force_refresh = (
            os.getenv("TRANSCRIPTION_FORCE", "").strip().lower()
            in {"1", "true", "yes", "on"}
        )
        mirror_legacy = (
            os.getenv("TRANSCRIPTS_LEGACY_MIRROR", "").strip().lower()
            in {"1", "true", "yes", "on"}
        )

        words = run_transcription(filename, user_id, guest_ids=guest_ids)
        stem = Path(filename).stem
        import json as _json

        orig_new = tr_dir / f"{stem}.original.json"
        work_new = tr_dir / f"{stem}.json"
        orig_legacy = tr_dir / f"{stem}.original.words.json"
        work_legacy = tr_dir / f"{stem}.words.json"

        if force_refresh or (not orig_new.exists() and not orig_legacy.exists()):
            with open(orig_new, "w", encoding="utf-8") as fh:
                _json.dump(words, fh, ensure_ascii=False)
        if force_refresh or (not work_new.exists() and not work_legacy.exists()):
            with open(work_new, "w", encoding="utf-8") as fh:
                _json.dump(words, fh, ensure_ascii=False)

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

        if force_refresh:
            logging.info(
                "[transcribe] FORCED fresh transcripts for %s -> %s, %s%s",
                filename,
                orig_new.name,
                work_new.name,
                (
                    f", mirrored -> {orig_legacy.name}, {work_legacy.name}"
                    if mirror_legacy
                    else ""
                ),
            )
        else:
            logging.info(
                "[transcribe] cached transcripts for %s -> %s, %s%s",
                filename,
                orig_new.name,
                work_new.name,
                (
                    f", mirrored -> {orig_legacy.name}, {work_legacy.name}"
                    if mirror_legacy
                    else ""
                ),
            )

        result = {
            "ok": True,
            "filename": filename,
            "original": orig_new.name,
            "working": work_new.name,
        }
        notify_watchers_processed(filename)
        return result
    except Exception as exc:
        logging.warning("[transcribe] failed for %s: %s", filename, exc, exc_info=True)

        try:
            if os.getenv("TRANSCRIPTION_FAKE", "").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }:
                from pydub import AudioSegment as _AudioSegment

                src = MEDIA_DIR / filename
                audio = (
                    _AudioSegment.from_file(src)
                    if src.is_file()
                    else _AudioSegment.silent(duration=10_000)
                )
                duration_s = max(1.0, len(audio) / 1000.0)
                words = []
                current = 0.0
                idx = 0
                while current < duration_s:
                    token = "flubber" if idx % 10 == 5 else f"w{idx}"
                    words.append(
                        {
                            "word": token,
                            "start": round(current, 3),
                            "end": round(current + 0.3, 3),
                            "speaker": None,
                        }
                    )
                    current += 0.5
                    idx += 1

                tr_dir = TRANSCRIPTS_DIR
                tr_dir.mkdir(parents=True, exist_ok=True)
                import json as _json

                stem = Path(filename).stem
                orig_new = tr_dir / f"{stem}.original.json"
                work_new = tr_dir / f"{stem}.json"
                orig_legacy = tr_dir / f"{stem}.original.words.json"
                work_legacy = tr_dir / f"{stem}.words.json"
                mirror_legacy = (
                    os.getenv("TRANSCRIPTS_LEGACY_MIRROR", "").strip().lower()
                    in {"1", "true", "yes", "on"}
                )

                if not orig_new.exists() and not orig_legacy.exists():
                    with open(orig_new, "w", encoding="utf-8") as fh:
                        _json.dump(words, fh, ensure_ascii=False)
                if not work_new.exists() and not work_legacy.exists():
                    with open(work_new, "w", encoding="utf-8") as fh:
                        _json.dump(words, fh, ensure_ascii=False)
                if mirror_legacy:
                    try:
                        if orig_new.exists() and not orig_legacy.exists():
                            shutil.copyfile(orig_new, orig_legacy)
                        if work_new.exists() and not work_legacy.exists():
                            shutil.copyfile(work_new, work_legacy)
                    except Exception:
                        pass

                logging.info(
                    "[transcribe] DEV FAKE wrote %s, %s%s",
                    orig_new.name,
                    work_new.name,
                    (
                        f", mirrored -> {orig_legacy.name}, {work_legacy.name}"
                        if mirror_legacy
                        else ""
                    ),
                )
                result = {
                    "ok": True,
                    "filename": filename,
                    "original": orig_new.name,
                    "working": work_new.name,
                    "fake": True,
                }
                notify_watchers_processed(filename)
                return result
        except Exception as fallback_exc:
            logging.warning(
                "[transcribe] dev-fake fallback failed: %s",
                fallback_exc,
                exc_info=True,
            )

        return {"ok": False, "filename": filename, "error": str(exc)}
