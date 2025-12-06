"""Manual cut task and helpers."""

from __future__ import annotations

import logging
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

from pydub import AudioSegment
from sqlmodel import select

from .app import celery_app
from api.core.database import get_session
from api.core.paths import FINAL_DIR, MEDIA_DIR
from api.models.podcast import Episode
from infrastructure import storage

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


def _download_cloud_file(uri: str) -> Path | None:
    """Download file from cloud storage to a temporary file."""
    try:
        if uri.startswith("gs://"):
            parts = uri[5:].split("/", 1)
        elif uri.startswith("r2://"):
            parts = uri[5:].split("/", 1)
        else:
            return None
            
        if len(parts) != 2:
            return None
            
        bucket, key = parts
        data = storage.download_bytes(bucket, key)
        if not data:
            return None
            
        suffix = Path(key).suffix or ".mp3"
        fd, path = tempfile.mkstemp(suffix=suffix)
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
        return Path(path)
    except Exception as e:
        logging.getLogger("ppp.tasks.manual_cut").error(f"Download failed: {e}")
        return None


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

    # Determine source path (Cloud > Local)
    final_path = getattr(episode, "final_audio_path", None) or getattr(episode, "gcs_audio_path", None)
    src_path = None
    is_cloud = False
    
    if final_path and (str(final_path).startswith("gs://") or str(final_path).startswith("r2://")):
        log.info(f"Downloading cloud audio for editing: {final_path}")
        src_path = _download_cloud_file(str(final_path))
        is_cloud = True
    else:
        src_path = _resolve_source_path(final_path)

    if not src_path:
        log.error("manual_cut_episode: source file not found for episode %s (path=%s)", episode_id, final_path)
        return {"ok": False, "error": "source file missing"}

    try:
        audio = AudioSegment.from_file(src_path)
        total_length = len(audio)
    except Exception as exc:
        log.exception("manual_cut_episode: failed to load audio")
        if is_cloud and src_path and src_path.exists():
            try:
                os.unlink(src_path)
            except:
                pass
        return {"ok": False, "error": f"load failed: {exc}"}

    merged = _normalize_cuts(cuts)
    if not merged:
        if is_cloud and src_path and src_path.exists():
            try:
                os.unlink(src_path)
            except:
                pass
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
        if is_cloud and src_path and src_path.exists():
            try:
                os.unlink(src_path)
            except:
                pass
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

    # Export result
    if is_cloud:
        # Create temp output file
        fd, out_path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)
        out_path = Path(out_path)
    else:
        # Legacy local file behavior
        FINAL_DIR.mkdir(parents=True, exist_ok=True)
        base_stem = src_path.stem
        out_path = FINAL_DIR / f"{base_stem}-cut.mp3"
        suffix = 1
        while out_path.exists() and suffix < 100:
            out_path = FINAL_DIR / f"{base_stem}-cut-{suffix}.mp3"
            suffix += 1

    try:
        result.export(out_path, format="mp3", bitrate="192k")
    except Exception as exc:
        log.exception("manual_cut_episode: export failed")
        if is_cloud:
            try:
                os.unlink(src_path)
                if out_path.exists():
                    os.unlink(out_path)
            except:
                pass
        return {"ok": False, "error": f"export failed: {exc}"}

    # Upload if cloud
    new_uri = None
    if is_cloud:
        try:
            original_uri = str(final_path)
            # Extract bucket/key logic again or just use a new key
            if original_uri.startswith("gs://"):
                bucket, old_key = original_uri[5:].split("/", 1)
            elif original_uri.startswith("r2://"):
                bucket, old_key = original_uri[5:].split("/", 1)
            else:
                # Fallback
                bucket = None
                old_key = f"audio/{episode_id}.mp3"
            
            # Construct new key
            parent = str(Path(old_key).parent).replace("\\", "/")
            if parent == ".": parent = ""
            new_key = f"{parent}/{Path(old_key).stem}_cut_{uuid.uuid4().hex[:6]}.mp3"
            if new_key.startswith("/"): new_key = new_key[1:]
            
            with open(out_path, "rb") as f:
                new_uri = storage.upload_fileobj(None, new_key, f, content_type="audio/mpeg")
                
        except Exception as exc:
            log.exception("manual_cut_episode: upload failed")
            return {"ok": False, "error": f"upload failed: {exc}"}
        finally:
            # Cleanup
            try:
                os.unlink(src_path)
                os.unlink(out_path)
            except:
                pass
    else:
        new_uri = out_path.name # Legacy: just filename

    try:
        if is_cloud and new_uri:
            episode.gcs_audio_path = new_uri
            episode.final_audio_path = new_uri
        elif not is_cloud:
            episode.final_audio_path = new_uri
            
        try:
            episode.duration_ms = len(result)
        except Exception:
            pass
        session.add(episode)
        session.commit()
    except Exception:
        session.rollback()
        log.exception("manual_cut_episode: failed to update episode")
        return {"ok": False, "error": "db update failed"}

    return {
        "ok": True,
        "final_audio_path": str(new_uri),
        "duration_ms": len(result),
    }

