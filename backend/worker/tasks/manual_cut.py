"""Manual cut task and helpers."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydub import AudioSegment
from sqlmodel import select

from worker.tasks import celery_app
from api.core.database import get_session
from api.core.paths import FINAL_DIR, MEDIA_DIR
from api.models.podcast import Episode

from uuid import UUID


def _normalize_cuts(cuts: list[dict[str, Any]] | None) -> list[dict[str, int]]:
    """Normalize, sort and merge manual cut ranges."""

    try:
        norm: list[dict[str, int]] = []
        for cut in cuts or []:
            try:
                raw_start = cut.get("start_ms", 0)
                raw_end = cut.get("end_ms", 0)
                start = int(raw_start if raw_start is not None else 0)
                end = int(raw_end if raw_end is not None else 0)
            except Exception:
                continue
            if end > start and (end - start) >= 20:
                norm.append({"start_ms": start, "end_ms": end})

        norm.sort(key=lambda item: item["start_ms"])
        merged: list[dict[str, int]] = []
        for cut in norm:
            if not merged or cut["start_ms"] > merged[-1]["end_ms"]:
                merged.append(dict(cut))
            else:
                merged[-1]["end_ms"] = max(merged[-1]["end_ms"], cut["end_ms"])
        return merged
    except Exception:
        return []


def _resolve_source_path(final_audio_path: str | Path | None) -> Path | None:
    """Resolve the absolute path for the episode's final audio."""

    if not final_audio_path:
        return None

    try:
        src_name = Path(str(final_audio_path)).name
    except Exception:
        return None

    candidates = [FINAL_DIR / src_name, MEDIA_DIR / src_name]
    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate
        except Exception:
            continue
    return None


@celery_app.task(name="manual_cut_episode")
def manual_cut_episode(episode_id: str, cuts: list[dict[str, Any]]):
    """Remove the specified cut ranges from the episode's final audio."""

    log = logging.getLogger("ppp.tasks.manual_cut")
    session = next(get_session())

    try:
        episode = session.exec(
            select(Episode).where(Episode.id == UUID(str(episode_id)))
        ).first()
    except Exception:
        episode = None

    if not episode:
        log.error("manual_cut_episode: episode not found %s", episode_id)
        return {"ok": False, "error": "episode not found"}

    src_path = _resolve_source_path(getattr(episode, "final_audio_path", None))
    if not src_path:
        log.error("manual_cut_episode: source file not found for episode %s", episode_id)
        return {"ok": False, "error": "source file missing"}

    try:
        audio = AudioSegment.from_file(src_path)
        total_length = len(audio)
    except Exception as exc:  # pragma: no cover - defensive logging
        log.exception("manual_cut_episode: failed to load audio")
        return {"ok": False, "error": f"load failed: {exc}"}

    merged = _normalize_cuts(cuts)
    if not merged:
        return {
            "ok": True,
            "message": "no cuts to apply",
            "final_audio_path": str(getattr(episode, "final_audio_path", "")),
            "duration_ms": total_length,
        }

    to_remove: list[tuple[int, int]] = []
    for cut in merged:
        start = max(0, min(total_length, int(cut["start_ms"])))
        end = max(0, min(total_length, int(cut["end_ms"])))
        if end > start:
            to_remove.append((start, end))

    to_remove.sort(key=lambda item: item[0])
    if not to_remove:
        return {
            "ok": True,
            "message": "no valid cuts after clamp",
            "final_audio_path": str(getattr(episode, "final_audio_path", "")),
            "duration_ms": total_length,
        }

    kept_segments: list[AudioSegment] = []
    cursor = 0
    for start, end in to_remove:
        if start > cursor:
            kept_segments.append(audio[cursor:start])
        cursor = end
    if cursor < total_length:
        kept_segments.append(audio[cursor:total_length])

    try:
        result = kept_segments[0]
        for segment in kept_segments[1:]:
            result += segment
    except Exception:
        result = audio

    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    base_stem = src_path.stem
    out_path = FINAL_DIR / f"{base_stem}-cut.mp3"
    suffix = 1
    while out_path.exists() and suffix < 100:
        out_path = FINAL_DIR / f"{base_stem}-cut-{suffix}.mp3"
        suffix += 1

    try:
        result.export(out_path, format="mp3")
    except Exception as exc:  # pragma: no cover - defensive logging
        log.exception("manual_cut_episode: export failed")
        return {"ok": False, "error": f"export failed: {exc}"}

    try:
        episode.final_audio_path = out_path.name
        try:
            episode.duration_ms = len(result)
        except Exception:
            pass
        session.add(episode)
        session.commit()
    except Exception:  # pragma: no cover - database failure path
        session.rollback()
        log.exception("manual_cut_episode: failed to update episode")
        return {"ok": False, "error": "db update failed"}

    return {
        "ok": True,
        "final_audio_path": out_path.name,
        "duration_ms": len(result),
    }

