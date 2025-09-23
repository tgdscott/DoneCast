# api/routers/media/write.py

import json
from uuid import uuid4, UUID
from typing import List, Optional
from pathlib import Path
from datetime import datetime
import logging
import os

from fastapi import (
    APIRouter,
    HTTPException,
    status,
    Depends,
    UploadFile,
    File,
    Form,
    Request,
)
from sqlmodel import Session, select

from api.core.paths import MEDIA_DIR
from api.models.podcast import MediaItem, MediaCategory
from api.models.user import User
from api.core.database import get_session
from api.routers.auth import get_current_user
from infrastructure.tasks_client import enqueue_http_task
from infrastructure.gcs import upload_bytes, upload_fileobj

from .schemas import MediaItemUpdate
from .common import sanitize_name, copy_with_limit

# Optional rate limiter (SlowAPI); only decorate if available and app wired it
try:
    from api.limits import limiter as _limiter  # app.state.limiter is set in app startup
except Exception:  # pragma: no cover
    _limiter = None  # type: ignore

router = APIRouter(prefix="/media", tags=["Media Library"])

MEDIA_BUCKET = os.getenv("MEDIA_BUCKET")


def _require_bucket() -> str:
    bucket = MEDIA_BUCKET or os.getenv("MEDIA_BUCKET")
    if not bucket:
        raise HTTPException(status_code=500, detail="Media storage bucket is not configured. Set the MEDIA_BUCKET environment variable.")
    return bucket


def parse_friendly_names(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        import json

        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(x) for x in parsed]
        return [str(parsed)]
    except Exception:
        s = raw.strip().strip("'").strip('"')
        if s.startswith("[") and s.endswith("]"):
            s = s[1:-1]
        return [p.strip() for p in s.split(",") if p.strip()]


@router.post("/upload/{category}", response_model=List[MediaItem], status_code=status.HTTP_201_CREATED)
@(_limiter.limit("30/hour") if _limiter and hasattr(_limiter, "limit") else (lambda f: f))
async def upload_media_files(
    request: Request,                              # <-- required so SlowAPI can see "request"
    category: MediaCategory,
    files: List[UploadFile] = File(...),
    friendly_names: Optional[str] = Form(None),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> List[MediaItem]:
    """
    Upload one or more media files with optional friendly names.
    - Enforces type/extension by category
    - Per-category size caps
    - For main_content, assigns expires_at and fires async transcription task
    """
    created_items: List[MediaItem] = []
    names = parse_friendly_names(friendly_names)

    MB = 1024 * 1024
    CATEGORY_SIZE_LIMITS = {
        MediaCategory.main_content: 500 * MB,
        MediaCategory.intro: 50 * MB,
        MediaCategory.outro: 50 * MB,
        MediaCategory.music: 50 * MB,
        MediaCategory.commercial: 50 * MB,
        MediaCategory.sfx: 25 * MB,
        MediaCategory.podcast_cover: 10 * MB,
        MediaCategory.episode_cover: 10 * MB,
    }

    AUDIO_PREFIX = "audio/"
    IMAGE_PREFIX = "image/"
    CATEGORY_TYPE_PREFIX = {
        MediaCategory.main_content: AUDIO_PREFIX,
        MediaCategory.intro: AUDIO_PREFIX,
        MediaCategory.outro: AUDIO_PREFIX,
        MediaCategory.music: AUDIO_PREFIX,
        MediaCategory.commercial: AUDIO_PREFIX,
        MediaCategory.sfx: AUDIO_PREFIX,
        MediaCategory.podcast_cover: IMAGE_PREFIX,
        MediaCategory.episode_cover: IMAGE_PREFIX,
    }

    AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".webm", ".mp4"}
    IMAGE_EXTS = {".png", ".jpg", ".jpeg"}

    def _validate_meta(f: UploadFile, cat: MediaCategory) -> None:
        ct = (getattr(f, "content_type", None) or "").lower()
        type_prefix = CATEGORY_TYPE_PREFIX.get(cat)
        if type_prefix and not ct.startswith(type_prefix):
            expected = "audio" if type_prefix == AUDIO_PREFIX else "image"
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type '{ct or 'unknown'}'. Expected {expected} file for category '{cat.value}'.",
            )
        ext = Path(f.filename or "").suffix.lower()
        if not ext:
            raise HTTPException(status_code=400, detail="File must have an extension.")
        allowed = AUDIO_EXTS if type_prefix == AUDIO_PREFIX else IMAGE_EXTS
        if ext not in allowed:
            raise HTTPException(status_code=400, detail=f"Unsupported file extension '{ext}'.")

    for i, file in enumerate(files):
        if not file.filename:
            continue

        _validate_meta(file, category)

        original_filename = Path(file.filename).stem
        default_friendly_name = " ".join(original_filename.split("_")).title()

        safe_orig = sanitize_name(file.filename)
        # GCS object key: user_id/category/uuid4_safe_filename
        gcs_key = f"{current_user.id}/{category.value}/{uuid4().hex}_{safe_orig}"

        # Prefer streaming upload to GCS without buffering entire file in memory
        max_bytes = CATEGORY_SIZE_LIMITS.get(category, 50 * MB)
        bucket = _require_bucket()
        content_type = file.content_type or "application/octet-stream"

        # SpooledTemporaryFile used by Starlette/UploadFile provides .file with potential ._file attribute
        # We will stream that file object to GCS. First, try to determine size cheaply.
        raw_f = getattr(file, "file", None)
        file_size = None
        try:
            # Some implementations expose a ._file that is a SpooledTemporaryFile or disk file
            _inner = getattr(raw_f, "_file", raw_f)
            if _inner is not None and hasattr(_inner, "seek") and hasattr(_inner, "tell"):
                cur = _inner.tell()
                _inner.seek(0, 2)
                end = _inner.tell()
                _inner.seek(cur, 0)
                file_size = int(end)
        except Exception:
            file_size = None

        # Enforce size limit prior to upload when size is known
        if file_size is not None and file_size > max_bytes:
            raise HTTPException(status_code=413, detail="File too large.")

        # Upload from the underlying file object; if size unknown, GCS library will stream until EOF
        # Use a larger chunk for throughput
        try:
            if raw_f is None or not hasattr(raw_f, "read"):
                raise RuntimeError("no file object; fallback path")
            gcs_uri = upload_fileobj(bucket, gcs_key, raw_f, size=file_size, content_type=content_type, chunk_mb=8)
            bytes_written = file_size if file_size is not None else None
        except Exception as ex:
            # As a fallback, buffer in chunks enforcing size limit and upload as bytes (smaller files)
            bytes_written = 0
            buf = bytearray()
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > max_bytes:
                    raise HTTPException(status_code=413, detail="File too large.")
                buf.extend(chunk)
            gcs_uri = upload_bytes(bucket, gcs_key, bytes(buf), content_type)

        friendly_name = names[i] if i < len(names) and str(names[i]).strip() else default_friendly_name

        media_item = MediaItem(
            filename=gcs_uri,  # Store gs:// URI
            friendly_name=str(friendly_name),
            content_type=(file.content_type or None),
            filesize=(int(bytes_written) if isinstance(bytes_written, int) and bytes_written >= 0 else None),
            user_id=current_user.id,
            category=category,
        )

        # Assign expires_at for raw uploads (main_content): 2am PT +14 days rule
        try:
            if category == MediaCategory.main_content:
                from api.main import _compute_pt_expiry  # type: ignore
                now_utc = datetime.utcnow()
                media_item.expires_at = _compute_pt_expiry(now_utc)
        except Exception:
            # don't fail upload if expiry calc wiring changes
            pass

        session.add(media_item)
        created_items.append(media_item)

        # Kick transcription (best-effort)
        try:
            if category == MediaCategory.main_content:
                task = enqueue_http_task("/api/tasks/transcribe", {"filename": gcs_uri})
                logging.info("event=upload.enqueue ok=true filename=%s task_name=%s", gcs_uri, task.get("name"))
        except Exception:
            # background task is best-effort; never fail the upload
            pass

        # Structured log: upload.receive
        logging.info(
            "event=upload.receive user_id=%s category=%s filename=%s size=%d content_type=%s",
            current_user.id, category.value, file.filename, bytes_written, file.content_type or ""
        )

    session.commit()
    for item in created_items:
        session.refresh(item)

    return created_items


@router.put("/{media_id}", response_model=MediaItem)
def update_media_item_name(
    media_id: UUID,
    media_update: MediaItemUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> MediaItem:
    media_item = session.get(MediaItem, media_id)
    if not media_item or media_item.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Media item not found.")

    if media_update.friendly_name is not None:
        media_item.friendly_name = media_update.friendly_name
    if media_update.trigger_keyword is not None:
        media_item.trigger_keyword = media_update.trigger_keyword.strip().lower() or None

    session.add(media_item)
    session.commit()
    session.refresh(media_item)
    return media_item


@router.delete("/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_media_item(
    media_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    statement = select(MediaItem).where(
        MediaItem.id == media_id,
        MediaItem.user_id == current_user.id,
    )
    media_item = session.exec(statement).one_or_none()

    if not media_item:
        raise HTTPException(status_code=404, detail="Media item not found or you don't have permission to delete it.")

    file_path = MEDIA_DIR / media_item.filename
    if file_path.exists():
        try:
            file_path.unlink()
        except Exception:
            # don't block DB delete if FS cleanup fails
            pass

    session.delete(media_item)
    session.commit()
    return None
