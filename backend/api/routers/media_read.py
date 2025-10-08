from collections import defaultdict
import json
import logging
import os
from pathlib import Path
from typing import Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy import text as _sa_text
from sqlmodel import Session, select

from api.core.database import get_session
from api.core.paths import TRANSCRIPTS_DIR
from api.models.podcast import MediaCategory, MediaItem
from api.models.transcription import MediaTranscript, TranscriptionWatch
from api.models.user import User
from api.routers.ai_suggestions import _gather_user_sfx_entries
from api.routers.auth import get_current_user
from api.services.audio.transcript_io import load_transcript_json
from api.services.intent_detection import analyze_intents, get_user_commands

from .media_schemas import MainContentItem

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/media", tags=["Media Library"])


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


def _resolve_transcript_path(filename: str, session: Session | None = None) -> Path:
    """Resolve transcript path, downloading from GCS if missing locally.
    
    After Cloud Run deployments, local ephemeral storage is wiped. This function
    checks GCS for transcripts that were previously uploaded and downloads them
    back to local storage so the frontend can see transcript_ready=True.
    """
    stem = Path(filename).stem
    candidates = [
        TRANSCRIPTS_DIR / f"{stem}.json",
        TRANSCRIPTS_DIR / f"{stem}.words.json",
        TRANSCRIPTS_DIR / f"{stem}.original.json",
        TRANSCRIPTS_DIR / f"{stem}.original.words.json",
    ]
    
    # Check if any candidate exists locally
    for candidate in candidates:
        if candidate.exists():
            return candidate
    
    # No local file found - try to recover from GCS using MediaTranscript metadata
    if session is not None:
        try:
            # Query MediaTranscript for this filename to get GCS location
            stmt = select(MediaTranscript).where(MediaTranscript.filename == filename)
            transcript_record = session.exec(stmt).first()
            
            if transcript_record and transcript_record.transcript_meta_json:
                meta = json.loads(transcript_record.transcript_meta_json)
                gcs_uri = meta.get("gcs_json") or meta.get("gcs_uri")
                bucket_stem = meta.get("bucket_stem") or meta.get("safe_stem") or stem
                
                if gcs_uri and gcs_uri.startswith("gs://"):
                    # Parse gs://bucket/path format
                    parts = gcs_uri.replace("gs://", "").split("/", 1)
                    if len(parts) == 2:
                        bucket_name, key = parts
                    else:
                        # Fallback: use env bucket + deterministic path
                        bucket_name = (os.getenv("TRANSCRIPTS_BUCKET") or "").strip()
                        key = f"transcripts/{bucket_stem}.json"
                elif gcs_uri:
                    # Already a key path like "transcripts/abc.json"
                    bucket_name = (os.getenv("TRANSCRIPTS_BUCKET") or "").strip()
                    key = gcs_uri
                else:
                    # No GCS URI in metadata - try deterministic location
                    bucket_name = (os.getenv("TRANSCRIPTS_BUCKET") or "").strip()
                    key = f"transcripts/{bucket_stem}.json"
                
                if bucket_name and key:
                    try:
                        from infrastructure.gcs import download_bytes
                        
                        content = download_bytes(bucket_name, key)
                        if content:
                            # Restore to local path
                            TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
                            local_path = TRANSCRIPTS_DIR / f"{stem}.json"
                            local_path.write_bytes(content)
                            logger.info(
                                "[media_read] Recovered transcript from gs://%s/%s to %s",
                                bucket_name, key, local_path
                            )
                            return local_path
                    except Exception as e:
                        logger.warning(
                            "[media_read] Could not download transcript from GCS for %s: %s",
                            filename, e
                        )
        except Exception as e:
            logger.warning("[media_read] Error checking MediaTranscript for %s: %s", filename, e)
    
    # Return first candidate even if it doesn't exist (for backwards compatibility)
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
    """Return main content uploads along with transcript/intents metadata."""

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
    for item in uploads:
        filename = str(item.filename)
        # Pass session so we can query MediaTranscript and recover from GCS if needed
        transcript_path = _resolve_transcript_path(filename, session=session)
        ready = transcript_path.exists()
        # If a worker already notified watchers for this filename, consider it ready
        if not ready:
            try:
                wlist = watch_map.get(filename, [])
                if any(getattr(w, "notified_at", None) is not None for w in wlist):
                    ready = True
            except Exception:
                pass
        intents = {}
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

    return results

