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
from api.models.transcription import TranscriptionWatch
from api.models.user import User
from api.core.database import get_session
from api.routers.auth import get_current_user
from infrastructure.tasks_client import enqueue_http_task
from infrastructure.gcs import upload_bytes, upload_fileobj, delete_gcs_blob

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
    request: Request,                              # required so SlowAPI can see "request"
    category: MediaCategory,
    files: List[UploadFile] | None = File(None),
    single_file: UploadFile | None = File(None),
    friendly_names: Optional[str] = Form(None),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    notify_when_ready: Optional[str] = Form(default=None),
    notify_email: Optional[str] = Form(default=None),
) -> List[MediaItem]:
    """
    Upload one or more media files with optional friendly names.
    - Enforces type/extension by category
    - Per-category size caps
    - For main_content, assigns expires_at and fires async transcription task
    """
    created_items: List[MediaItem] = []
    # Track gs:// objects created in this request so we can delete them on DB failure
    uploaded_objects: list[tuple[str, str]] = []  # (bucket, key)
    names = parse_friendly_names(friendly_names)

    notify_requested = False
    if isinstance(notify_when_ready, str):
        notify_requested = notify_when_ready.strip().lower() in {"1", "true", "yes", "on"}
    elif notify_when_ready:
        notify_requested = True

    notify_target = (notify_email or "").strip() if notify_email else ""
    if notify_requested and not notify_target:
        try:
            notify_target = (current_user.email or "").strip() if hasattr(current_user, "email") else ""
        except Exception:
            notify_target = ""
    if notify_target and "@" not in notify_target:
        notify_target = ""

    def _queue_watch(filename: str, friendly: str) -> None:
        if not filename or category != MediaCategory.main_content:
            return

        # Always record a watch so in-app notifications fire even when the
        # user didn't request an email. Only persist an email target when one
        # was explicitly supplied/derived.
        email_target = (
            notify_target if notify_requested and notify_target else None
        )
        try:
            existing_watch = session.exec(
                select(TranscriptionWatch).where(
                    TranscriptionWatch.user_id == current_user.id,
                    TranscriptionWatch.filename == filename,
                )
            ).first()
        except Exception:
            existing_watch = None

        friendly_clean = (friendly or "").strip() or Path(filename).stem

        if existing_watch:
            existing_watch.notify_email = email_target
            existing_watch.friendly_name = friendly_clean
            existing_watch.notified_at = None
            existing_watch.last_status = "queued"
            session.add(existing_watch)
        else:
            session.add(
                TranscriptionWatch(
                    user_id=current_user.id,
                    filename=filename,
                    friendly_name=friendly_clean,
                    notify_email=email_target,
                    last_status="queued",
                )
            )

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
        # Tolerate missing or generic content types from some clients; enforce when clearly mismatched
        if type_prefix and ct not in ("", "application/octet-stream") and not ct.startswith(type_prefix):
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

    # Normalize inputs: support both 'files' (list) and single 'file'
    incoming_files: List[UploadFile] = []
    if files:
        incoming_files.extend([f for f in files if f is not None])
    if single_file is not None:
        incoming_files.append(single_file)
    if not incoming_files:
        raise HTTPException(status_code=400, detail="No files provided. Expected form field 'files' or 'file'.")

    for i, uf in enumerate(incoming_files):
        if not uf.filename:
            continue

        _validate_meta(uf, category)

        # Determine proposed friendly name for this file (before any upload)
        original_filename = Path(uf.filename or "").stem
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
        content_type = uf.content_type or "application/octet-stream"

        # SpooledTemporaryFile used by Starlette/UploadFile provides .file with potential ._file attribute
        # We will stream that file object to GCS. First, try to determine size cheaply.
        raw_f = getattr(uf, "file", None)
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
                uf.filename, category.value, (file_size if file_size is not None else "unknown"), max_bytes, content_type
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
                import time
                t0 = time.time()
                # Allow tuning via env var GCS_CHUNK_MB
                chunk_mb_env = os.getenv("GCS_CHUNK_MB")
                # chunk_mb_val = int(chunk_mb_env) if chunk_mb_env and chunk_mb_env.isdigit() else None
                uri = upload_fileobj(bucket_name, object_key, raw_f, content_type=content_type)
                dt = max(0.0001, time.time() - t0)
                written = file_size if file_size is not None else None
                try:
                    mb = (written or 0) / (1024*1024)
                    logging.info(
                        "event=upload.stream_ok path=%s bucket=%s key=%s bytes=%s seconds=%.3f mbps=%.2f chunk_mb=%s dev_local=%s",
                        uri, bucket_name, object_key, (written or -1), dt, (mb*8.0/dt if dt>0 else 0.0), os.getenv("GCS_CHUNK_MB"), str(os.getenv("APP_ENV")).lower().startswith("dev")
                    )
                except Exception:
                    pass
                return uri, written
            except Exception:
                # Fallback: buffer and upload as bytes (with size enforcement)
                import time
                t0 = time.time()
                written = 0
                buf = bytearray()
                while True:
                    chunk = await uf.read(1024 * 1024)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > max_bytes:
                        try:
                            logging.warning(
                                "event=upload.reject_too_large filename=%s category=%s bytes=%s limit=%s",
                                uf.filename, category.value, written, max_bytes
                            )
                        except Exception:
                            pass
                        raise HTTPException(status_code=413, detail="File too large.")
                    buf.extend(chunk)
                uri = upload_bytes(bucket_name, object_key, bytes(buf), content_type)
                dt = max(0.0001, time.time() - t0)
                try:
                    mb = (written or 0) / (1024*1024)
                    logging.info(
                        "event=upload.buffer_ok path=%s bucket=%s key=%s bytes=%s seconds=%.3f mbps=%.2f dev_local=%s",
                        uri, bucket_name, object_key, (written or -1), dt, (mb*8.0/dt if dt>0 else 0.0), str(os.getenv("APP_ENV")).lower().startswith("dev")
                    )
                except Exception:
                    pass
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
                        target_key = Path(uf.filename or "").name

            uri, written = await _upload_to(target_bucket, target_key)

            # Normalize filename to whatever form was already stored (do not force gs:// if legacy value)
            existing_item.content_type = (uf.content_type or None)
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
            try:
                _queue_watch(str(existing_item.filename or ""), str(existing_item.friendly_name or fn_norm))
            except Exception:
                pass
            # Structured log: overwrite
            try:
                logging.info(
                    "event=upload.overwrite user_id=%s category=%s name=%s key=%s",
                    current_user.id, category.value, fn_norm, target_key
                )
            except Exception:
                pass
            # Kick transcription on overwrite for main content as well (best-effort)
            try:
                if category == MediaCategory.main_content:
                    logging.info(
                        "event=upload.enqueue attempt=true (overwrite) filename=%s cfg_project=%s cfg_loc=%s cfg_queue=%s cfg_base=%s dev=%s",
                        existing_item.filename,
                        os.getenv("GOOGLE_CLOUD_PROJECT"), os.getenv("TASKS_LOCATION"), os.getenv("TASKS_QUEUE"), os.getenv("TASKS_URL_BASE"), _is_dev_env()
                    )
                    task = enqueue_http_task("/api/tasks/transcribe", {"filename": existing_item.filename})
                    logging.info("event=upload.enqueue ok=true (overwrite) filename=%s task_name=%s", existing_item.filename, task.get("name"))
            except Exception as enqueue_err:
                logging.warning(
                    "event=upload.enqueue ok=false (overwrite) filename=%s err=%s hint=%s",
                    existing_item.filename,
                    enqueue_err,
                    f"Check Cloud Tasks config GOOGLE_CLOUD_PROJECT={os.getenv('GOOGLE_CLOUD_PROJECT')} TASKS_LOCATION={os.getenv('TASKS_LOCATION')} TASKS_QUEUE={os.getenv('TASKS_QUEUE')} TASKS_URL_BASE={os.getenv('TASKS_URL_BASE')} (dev={_is_dev_env()})",
                )
        else:
            # No existing item with this name. For enforced categories, block duplicates within the same request batch
            if category in ENFORCE_UNIQUE:
                if fn_key in batch_names_lower:
                    raise HTTPException(
                        status_code=409,
                        detail=f"Duplicate name in upload: '{fn_norm}'. Each uploaded item must have a unique name.",
                    )
                batch_names_lower.add(fn_key)

            # No overwrite case -> upload to a fresh object path and create a new media item
            safe_orig = sanitize_name(uf.filename or "")
            gcs_key = f"{current_user.id}/{category.value}/{uuid4().hex}_{safe_orig}"
            uri, written = await _upload_to(default_bucket, gcs_key)
            # Remember this object so we can clean it up if DB commit fails
            try:
                if uri.startswith("gs://"):
                    path_part = uri[5:]
                    bname, _, kpart = path_part.partition('/')
                    if bname and kpart:
                        uploaded_objects.append((bname, kpart))
            except Exception:
                pass

            media_item = MediaItem(
                filename=uri,  # Store gs:// URI when available
                friendly_name=str(fn_norm),
                content_type=(uf.content_type or None),
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
            try:
                _queue_watch(str(media_item.filename or ""), str(media_item.friendly_name or fn_norm))
            except Exception:
                pass

            # Kick transcription (best-effort)
            try:
                if category == MediaCategory.main_content:
                    logging.info("event=upload.enqueue attempt=true filename=%s cfg_project=%s cfg_loc=%s cfg_queue=%s cfg_base=%s dev=%s",
                                 media_item.filename,
                                 os.getenv("GOOGLE_CLOUD_PROJECT"), os.getenv("TASKS_LOCATION"), os.getenv("TASKS_QUEUE"), os.getenv("TASKS_URL_BASE"), _is_dev_env())
                    task = enqueue_http_task("/api/tasks/transcribe", {"filename": media_item.filename})
                    logging.info("event=upload.enqueue ok=true filename=%s task_name=%s", media_item.filename, task.get("name"))
            except Exception as enqueue_err:
                # background task is best-effort; never fail the upload, but do log why it's not enqueued
                logging.warning(
                    "event=upload.enqueue ok=false filename=%s err=%s hint=%s",
                    media_item.filename,
                    enqueue_err,
                    f"Check Cloud Tasks config GOOGLE_CLOUD_PROJECT={os.getenv('GOOGLE_CLOUD_PROJECT')} TASKS_LOCATION={os.getenv('TASKS_LOCATION')} TASKS_QUEUE={os.getenv('TASKS_QUEUE')} TASKS_URL_BASE={os.getenv('TASKS_URL_BASE')} (dev={_is_dev_env()})",
                )

            # Structured log: upload.receive
            logging.info(
                "event=upload.receive user_id=%s category=%s filename=%s size=%d content_type=%s",
                current_user.id, category.value, uf.filename, media_item.filesize or -1, uf.content_type or ""
            )

    # Commit all rows; on failure, delete any newly uploaded objects to avoid orphans
    try:
        session.commit()
    except Exception as db_err:
        try:
            for (b, k) in uploaded_objects:
                try:
                    delete_gcs_blob(b, k)
                except Exception:
                    pass
        finally:
            try:
                session.rollback()
            except Exception:
                pass
        logging.error("event=upload.db_commit_failed err=%s items=%d", db_err, len(created_items))
        raise HTTPException(status_code=500, detail="Upload failed while saving to the database. Please retry.")
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
                delete_gcs_blob(bucket_name, key)
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
