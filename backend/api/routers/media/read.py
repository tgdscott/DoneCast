from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import text as _sa_text
from sqlmodel import Session, select

from api.core.database import get_session
from api.core.paths import MEDIA_DIR, TRANSCRIPTS_DIR
from api.models.podcast import MediaCategory, MediaItem
from api.models.transcription import TranscriptionWatch
from api.models.user import User
from api.routers.ai_suggestions import _gather_user_sfx_entries
from api.routers.auth import get_current_user
from infrastructure import gcs
from api.services.audio.transcript_io import load_transcript_json
from api.services.intent_detection import analyze_intents, get_user_commands

from .schemas import MainContentItem

router = APIRouter(prefix="/media", tags=["Media Library"])


logger = logging.getLogger(__name__)


def _storage_presence(filename: str) -> Optional[bool]:
    """Return True if the backing object exists, False if known missing."""

    cleaned = (filename or "").strip()
    if not cleaned:
        return False

    if cleaned.startswith("gs://"):
        remainder = cleaned[5:]
        bucket, _, key = remainder.partition("/")
        if not bucket or not key:
            return False
        try:
            return gcs.blob_exists(bucket, key)
        except Exception:  # pragma: no cover - defensive guard
            logger.debug("Failed to probe blob existence for %s", cleaned, exc_info=True)
            return None

    try:
        path_obj = Path(cleaned)
    except Exception:
        path_obj = None

    if path_obj is not None:
        try:
            if path_obj.exists():
                return True
        except Exception:
            pass

    candidates: List[Path] = []

    for candidate_str in (cleaned,):
        try:
            candidates.append((MEDIA_DIR / candidate_str).resolve(strict=False))
        except Exception:
            pass

    try:
        base_name = path_obj.name if path_obj is not None else Path(cleaned).name
    except Exception:
        base_name = cleaned

    for root in (MEDIA_DIR, Path("media_uploads"), Path.cwd() / "media_uploads"):
        try:
            candidates.append((root / base_name).resolve(strict=False))
        except Exception:
            continue

    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        try:
            if candidate.exists():
                return True
        except Exception:
            continue

    return False


@router.get("/", response_model=List[MediaItem])
async def list_user_media(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Retrieve the current user's media library, filtering out main content and covers."""

    allowed = [
        MediaCategory.intro,
        MediaCategory.outro,
        MediaCategory.music,
        MediaCategory.sfx,
        MediaCategory.commercial,
    ]
    statement = (
        select(MediaItem)
        .where(
            MediaItem.user_id == current_user.id,
            MediaItem.category.in_(allowed),  # type: ignore[attr-defined]
        )
        .order_by(_sa_text("created_at DESC"))
    )
    return session.exec(statement).all()


@router.get("/preview")
def preview_media(
    request: Request,
    id: Optional[str] = Query(default=None),
    path: Optional[str] = Query(default=None, description="gs:// path or local filename (dev)"),
    resolve: bool = Query(default=False, description="If true, return JSON {url} instead of redirect"),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Return a temporary URL (or redirect) to preview a media item."""

    from fastapi.responses import JSONResponse, RedirectResponse
    import os

    from api.core.paths import MEDIA_DIR
    from infrastructure.gcs import make_signed_url

    item: Optional[MediaItem] = None
    if id:
        try:
            from uuid import UUID as _UUID

            uid = _UUID(id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid id")
        item = session.get(MediaItem, uid)
        if not item or item.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Not found")
        path = item.filename

    if not path:
        raise HTTPException(status_code=400, detail="Missing id or path")

    if path.startswith("gs://"):
        p = path[5:]
        bucket, _, key = p.partition("/")
        if not bucket or not key:
            raise HTTPException(status_code=400, detail="Invalid gs path")
        try:
            url = make_signed_url(bucket, key, minutes=int(os.getenv("GCS_SIGNED_URL_TTL_MIN", "10")))
        except Exception as ex:
            raise HTTPException(status_code=500, detail=f"Failed to sign URL: {ex}")
        rel = None
    else:
        filename = path.lstrip("/\\")
        try:
            media_root = MEDIA_DIR.resolve()
        except Exception:
            media_root = MEDIA_DIR
        try:
            candidate = (MEDIA_DIR / filename).resolve(strict=False)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid path")

        try:
            relative_path = candidate.relative_to(media_root)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid path")

        rel = f"/static/media/{relative_path.as_posix()}"
        try:
            base = str(request.base_url).rstrip("/")
            url = f"{base}{rel}" if base else rel
        except Exception:
            url = rel

    if resolve:
        payload = {"url": url}
        if rel is not None:
            payload["path"] = rel
        return JSONResponse(payload)
    return RedirectResponse(url)


def _resolve_transcript_path(filename: str) -> Path:
    stem = Path(filename).stem
    candidates = [
        TRANSCRIPTS_DIR / f"{stem}.json",
        TRANSCRIPTS_DIR / f"{stem}.words.json",
        TRANSCRIPTS_DIR / f"{stem}.original.json",
        TRANSCRIPTS_DIR / f"{stem}.original.words.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _compute_duration(words) -> float | None:
    try:
        last_end = 0.0
        for word in words or []:
            try:
                end = float(word.get("end") or word.get("end_time") or 0.0)
            except Exception:
                end = 0.0
            if end > last_end:
                last_end = end
        return last_end if last_end > 0 else None
    except Exception:
        return None


@router.get("/main-content", response_model=List[MainContentItem])
async def list_main_content_uploads(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Return main-content uploads enriched with transcript metadata."""

    stmt = (
        select(MediaItem)
        .where(
            MediaItem.user_id == current_user.id,
            MediaItem.category == MediaCategory.main_content,
        )
        .order_by(_sa_text("created_at DESC"))
    )
    uploads = session.exec(stmt).all()

    watch_map: Dict[str, List[TranscriptionWatch]] = defaultdict(list)
    try:
        watch_stmt = select(TranscriptionWatch).where(TranscriptionWatch.user_id == current_user.id)
        for watch in session.exec(watch_stmt):
            watch_map[str(watch.filename)].append(watch)
    except Exception:
        watch_map = defaultdict(list)

    intents_cache: Dict[str, Dict] = {}
    try:
        commands_cfg = get_user_commands(current_user)
        sfx_entries = list(_gather_user_sfx_entries(session, current_user))
    except Exception:
        commands_cfg = {}
        sfx_entries = []

    results: List[MainContentItem] = []
    missing_items: List[MediaItem] = []
    for item in uploads:
        filename = str(item.filename)
        storage_state = _storage_presence(filename)
        if storage_state is False:
            missing_items.append(item)
            continue
        transcript_path = _resolve_transcript_path(filename)
        ready = transcript_path.exists()
        if not ready:
            try:
                wlist = watch_map.get(filename, [])
                if any(getattr(w, "notified_at", None) is not None for w in wlist):
                    ready = True
            except Exception:
                pass

        intents: Dict[str, object] = {}
        duration = None
        if ready:
            try:
                words = load_transcript_json(transcript_path)
            except Exception:
                words = []
            if words:
                key = transcript_path.as_posix()
                if key in intents_cache:
                    intents = intents_cache[key]
                else:
                    intents = analyze_intents(words, commands_cfg, sfx_entries)
                    intents_cache[key] = intents
                duration = _compute_duration(words)

        pending = any(w.notified_at is None for w in watch_map.get(filename, []))

        results.append(
            MainContentItem(
                id=item.id,
                filename=filename,
                friendly_name=item.friendly_name,
                created_at=item.created_at,
                expires_at=item.expires_at,
                transcript_ready=ready,
                intents=intents or {},
                notify_pending=pending,
                duration_seconds=duration,
            )
        )

    if missing_items:
        try:
            for stale in missing_items:
                session.delete(stale)
            session.commit()
            logger.info(
                "Pruned %s missing main-content uploads for user %s",
                len(missing_items),
                current_user.id,
            )
        except Exception:
            session.rollback()
            logger.warning(
                "Failed to prune missing main-content uploads for user %s",
                current_user.id,
                exc_info=True,
            )

    return results


__all__ = ["router"]

