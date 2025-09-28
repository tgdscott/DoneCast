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
from sqlalchemy import func

from api.core.paths import MEDIA_DIR
from api.models.podcast import MediaItem, MediaCategory, PodcastTemplate
from api.models.user import User
from api.core.database import get_session
from api.core.auth import get_current_user
from infrastructure.tasks_client import enqueue_http_task
from infrastructure.gcs import upload_bytes, upload_fileobj, delete_blob

from .schemas import MediaItemUpdate
from .common import sanitize_name, copy_with_limit

# Optional rate limiter (SlowAPI); only decorate if available and app wired it
try:
    from api.limits import limiter as _limiter  # app.state.limiter is set in app startup
except Exception:  # pragma: no cover
    _limiter = None  # type: ignore

router = APIRouter(prefix="/media", tags=["Media Library"])

MEDIA_BUCKET = os.getenv("MEDIA_BUCKET")

def _is_dev_env() -> bool:
    val = (os.getenv("APP_ENV") or os.getenv("ENV") or os.getenv("PYTHON_ENV") or "dev").strip().lower()
    return val in {"dev", "development", "local", "test", "testing"}


def _require_bucket() -> str:
    bucket = MEDIA_BUCKET or os.getenv("MEDIA_BUCKET")
    # In local/dev/test, allow a dummy bucket and store files on the local MEDIA_DIR via the dev GCS shim
    if not bucket and _is_dev_env():
        return "dev-bucket"
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

    # Track duplicates within this request batch
    batch_names_lower: set[str] = set()

    MB = 1024 * 1024
    CATEGORY_SIZE_LIMITS = {
        MediaCategory.main_content: 1536 * MB,  # 1.5 GB
        MediaCategory.intro: 50 * MB,
        MediaCategory.outro: 50 * MB,
        MediaCategory.music: 50 * MB,
        MediaCategory.commercial: 50 * MB,
        MediaCategory.sfx: 25 * MB,
        MediaCategory.podcast_cover: 15 * MB,
        MediaCategory.episode_cover: 15 * MB,
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

        # Determine proposed friendly name for this file (before any upload)
        original_filename = Path(file.filename).stem
        default_friendly_name = " ".join(original_filename.split("_")).title()
        friendly_name = names[i] if i < len(names) and str(names[i]).strip() else default_friendly_name
        fn_norm = str(friendly_name).strip() or default_friendly_name
        fn_key = fn_norm.lower()

        # Only enforce uniqueness for specific library categories. For episode/podcast covers
        # and main content, duplicates are allowed.
        ENFORCE_UNIQUE = {
            MediaCategory.intro,
            MediaCategory.outro,
            MediaCategory.sfx,
        }

        # Prepare upload environment
        max_bytes = CATEGORY_SIZE_LIMITS.get(category, 50 * MB)
        default_bucket = _require_bucket()
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
        try:
            logging.info(
                "event=upload.precheck filename=%s category=%s size=%s limit=%s content_type=%s",
                file.filename, category.value, (file_size if file_size is not None else "unknown"), max_bytes, content_type
            )
        except Exception:
            pass
        if file_size is not None and file_size > max_bytes:
            raise HTTPException(status_code=413, detail="File too large.")
        # Helper to stream upload to a specific bucket/key
        async def _upload_to(bucket_name: str, object_key: str):
            nonlocal file_size
            # Prefer streaming upload from underlying file object
            try:
                if raw_f is None or not hasattr(raw_f, "read"):
                    raise RuntimeError("no file object; fallback path")
                uri = upload_fileobj(bucket_name, object_key, raw_f, size=file_size, content_type=content_type, chunk_mb=8)
                written = file_size if file_size is not None else None
                return uri, written
            except Exception:
                # Fallback: buffer and upload as bytes (with size enforcement)
                written = 0
                buf = bytearray()
                while True:
                    chunk = await file.read(1024 * 1024)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > max_bytes:
                        try:
                            logging.warning(
                                "event=upload.reject_too_large filename=%s category=%s bytes=%s limit=%s",
                                file.filename, category.value, written, max_bytes
                            )
                        except Exception:
                            pass
                        raise HTTPException(status_code=413, detail="File too large.")
                    buf.extend(chunk)
                uri = upload_bytes(bucket_name, object_key, bytes(buf), content_type)
                return uri, written

        # If an item with the same friendly name already exists for this user/category, overwrite its file and return it
        existing_item = session.exec(
            select(MediaItem)
            .where(
                MediaItem.user_id == current_user.id,
                MediaItem.category == category,
                func.lower(MediaItem.friendly_name) == fn_key,
            )
        ).first()

        if existing_item is not None:
                # Parse target bucket/key from existing filename if gs://, else use default bucket and existing filename as key
                target_bucket = default_bucket
                target_key = str(existing_item.filename or "").strip()
                if target_key.startswith("gs://"):
                    try:
                        # gs://bucket/key...
                        without = target_key[len("gs://"):]
                        bname, _, kpart = without.partition("/")
                        if bname and kpart:
                            target_bucket, target_key = bname, kpart
                    except Exception:
                        # Fall back to default bucket and original key sans prefix
                        try:
                            target_key = target_key.split("/", 3)[-1]
                        except Exception:
                            target_key = Path(file.filename or "").name

                uri, written = await _upload_to(target_bucket, target_key)

                # Normalize filename to whatever form was already stored (do not force gs:// if legacy value)
                existing_item.content_type = (file.content_type or None)
                try:
                    existing_item.filesize = int(written) if isinstance(written, int) and written >= 0 else None
                except Exception:
                    existing_item.filesize = None
                # Keep friendly_name and category unchanged
                session.add(existing_item)
                session.commit()
                session.refresh(existing_item)
                created_items.append(existing_item)
                batch_names_lower.add(fn_key)
                # Structured log: overwrite
                try:
                    logging.info(
                        "event=upload.overwrite user_id=%s category=%s name=%s key=%s",
                        current_user.id, category.value, fn_norm, target_key
                    )
                except Exception:
                    pass
                # Done with this file (we overwrote existing item)
                continue

        # No existing item with this name. For enforced categories, block duplicates within the same request batch
        if category in ENFORCE_UNIQUE:
            if fn_key in batch_names_lower:
                raise HTTPException(
                    status_code=409,
                    detail=f"Duplicate name in upload: '{fn_norm}'. Each uploaded item must have a unique name.",
                )
            batch_names_lower.add(fn_key)

        # No overwrite case -> upload to a fresh object path and create a new media item
        safe_orig = sanitize_name(file.filename or "")
        gcs_key = f"{current_user.id}/{category.value}/{uuid4().hex}_{safe_orig}"
        uri, written = await _upload_to(default_bucket, gcs_key)

        media_item = MediaItem(
            filename=uri,  # Store gs:// URI when available
            friendly_name=str(fn_norm),
            content_type=(file.content_type or None),
            filesize=(int(written) if isinstance(written, int) and written >= 0 else None),
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
                task = enqueue_http_task("/api/tasks/transcribe", {"filename": media_item.filename})
                logging.info("event=upload.enqueue ok=true filename=%s task_name=%s", media_item.filename, task.get("name"))
        except Exception:
            # background task is best-effort; never fail the upload
            pass

        # Structured log: upload.receive
        logging.info(
            "event=upload.receive user_id=%s category=%s filename=%s size=%d content_type=%s",
            current_user.id, category.value, file.filename, media_item.filesize or -1, file.content_type or ""
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
        new_name = (media_update.friendly_name or "").strip()
        if not new_name:
            raise HTTPException(status_code=400, detail="Name cannot be empty.")
        # Enforce unique friendly_name (case-insensitive) for this user, excluding the current item
        # Skip uniqueness for main_content category
        try:
            from api.models.podcast import MediaCategory as _MC
            is_main = (media_item.category == _MC.main_content)
        except Exception:
            is_main = False
        if not is_main:
            rows = session.exec(
                select(MediaItem.id, MediaItem.friendly_name)
                .where(MediaItem.user_id == current_user.id)
            ).all()
            for (mid, fname) in rows:
                if mid != media_id and fname and fname.strip().lower() == new_name.lower():
                    raise HTTPException(status_code=409, detail=f"A media item named '{new_name}' already exists.")
        media_item.friendly_name = new_name
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

    # Prevent deletion if this media is referenced by any of the user's templates
    try:
        # Build a set of names that templates might reference
        filename_full = str(media_item.filename or "")
        # If gs://bucket/key, take the last component after '/'
        filename_base = filename_full.rsplit('/', 1)[-1]
        candidate_names = {filename_full, filename_base}

        in_use_by: list[str] = []
        tpls = session.exec(
            select(PodcastTemplate).where(PodcastTemplate.user_id == current_user.id)
        ).all()
        for tpl in tpls:
            ref = False
            try:
                segs = json.loads(getattr(tpl, 'segments_json', '[]') or '[]')
                for s in segs or []:
                    src = (s or {}).get('source') or {}
                    if (src.get('source_type') == 'static'):
                        fn = str(src.get('filename') or '')
                        if fn and (fn in candidate_names or fn.rsplit('/', 1)[-1] in candidate_names):
                            ref = True; break
                if not ref:
                    rules = json.loads(getattr(tpl, 'background_music_rules_json', '[]') or '[]')
                    for r in rules or []:
                        fn = str(r.get('music_filename') or '')
                        if fn and (fn in candidate_names or fn.rsplit('/', 1)[-1] in candidate_names):
                            ref = True; break
            except Exception:
                # If parsing fails, assume no reference and continue
                ref = False
            if ref:
                name = getattr(tpl, 'name', None) or str(getattr(tpl, 'id', 'template'))
                in_use_by.append(name)
        if in_use_by:
            raise HTTPException(
                status_code=409,
                detail={
                    "detail": "This media is used in one or more templates and cannot be deleted.",
                    "templates": in_use_by,
                },
            )
    except HTTPException:
        raise
    except Exception:
        # On error, be safe and block deletion rather than risk breaking templates
        raise HTTPException(status_code=409, detail="Unable to verify template references; deletion blocked. Try again later.")

    # The filename can be a gs:// URI (prod) or a simple filename (local dev).
    # We need to handle both cases for deletion.
    if media_item.filename.startswith("gs://"):
        try:
            path_part = media_item.filename[5:]
            bucket_name, _, key = path_part.partition('/')
            if bucket_name and key:
                delete_blob(bucket_name, key)
        except Exception:
            # don't block DB delete if FS cleanup fails
            pass
    else:
        # Fallback for local files (as used in the dev sandbox)
        file_path = MEDIA_DIR / media_item.filename
        if file_path.exists():
            try:
                file_path.unlink()
            except Exception:
                pass

    session.delete(media_item)
    session.commit()
    return None
