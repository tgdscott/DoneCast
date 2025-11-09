import shutil
import json
from uuid import uuid4
import subprocess
import os
from collections import defaultdict
from fastapi import APIRouter, HTTPException, status, Depends, UploadFile, File, Form
from pydantic import BaseModel
from typing import List, Optional, Dict
from uuid import UUID
from pathlib import Path
from sqlmodel import Session, select
from sqlalchemy import text as _sa_text
from sqlalchemy import desc as _sa_desc

from ..models.podcast import MediaItem, MediaCategory
from ..models.transcription import TranscriptionWatch
from ..models.user import User
from ..core.database import get_session
from ..core.paths import TRANSCRIPTS_DIR
from api.routers.auth import get_current_user
from api.routers.ai_suggestions import _gather_user_sfx_entries
from api.services.audio.transcript_io import load_transcript_json
from api.services.intent_detection import analyze_intents, get_user_commands

router = APIRouter(
    prefix="/media",
    tags=["Media Library"],
)

from api.core.paths import MEDIA_DIR

class MediaItemUpdate(BaseModel):
    friendly_name: Optional[str] = None
    trigger_keyword: Optional[str] = None

@router.post("/upload/{category}", response_model=List[MediaItem], status_code=status.HTTP_201_CREATED)
async def upload_media_files(
    category: MediaCategory,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    files: List[UploadFile] = File(...),
    friendly_names: Optional[str] = Form(None)
):
    """Upload one or more media files with optional friendly names."""
    created_items = []
    names = json.loads(friendly_names) if friendly_names else []

    # Simple constraints and validators (server-side defense-in-depth)
    # Size caps (bytes)
    MB = 1024 * 1024
    CATEGORY_SIZE_LIMITS = {
        MediaCategory.main_content: 1536 * MB,  # 1.5 GB
        MediaCategory.intro: 50 * MB,
        MediaCategory.outro: 50 * MB,
        MediaCategory.music: 50 * MB,
        MediaCategory.commercial: 50 * MB,
        MediaCategory.sfx: 25 * MB,
        MediaCategory.podcast_cover: 10 * MB,
        MediaCategory.episode_cover: 10 * MB,
    }

    # Allowed content type prefixes by category
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

    # Allowed file extensions per category (lowercase)
    AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".webm", ".mp4"}
    IMAGE_EXTS = {".png", ".jpg", ".jpeg"}

    def _sanitize_name(name: str) -> str:
        # Keep base name only; strip directories
        base = Path(name).name
        # Restrict to safe charset
        import re
        base = re.sub(r"[^A-Za-z0-9._-]", "_", base).strip("._") or "file"
        return base[:200]

    def _validate_meta(f: UploadFile, cat: MediaCategory) -> None:
        # Content-type & extension gate
        ct = (getattr(f, "content_type", None) or "").lower()
        type_prefix = CATEGORY_TYPE_PREFIX.get(cat)
        if type_prefix and not ct.startswith(type_prefix):
            expected = "audio" if type_prefix == AUDIO_PREFIX else "image"
            raise HTTPException(status_code=400, detail=f"Invalid file type '{ct or 'unknown'}'. Expected {expected} file for category '{cat.value}'.")
        ext = Path(f.filename or "").suffix.lower()
        if not ext:
            raise HTTPException(status_code=400, detail="File must have an extension.")
        allowed = AUDIO_EXTS if type_prefix == AUDIO_PREFIX else IMAGE_EXTS
        if ext not in allowed:
            raise HTTPException(status_code=400, detail=f"Unsupported file extension '{ext}'.")
        # Light magic-byte sniff: read a small sample to validate claimed type (reset pointer after)
        try:
            head = f.file.read(16)
            f.file.seek(0)
            if type_prefix == AUDIO_PREFIX:
                # WAV RIFF, OGG, ID3 (MP3), fLaC
                sigs = [b"RIFF", b"OggS", b"ID3", b"fLaC", b"\xff\xfb"]
                if not any(head.startswith(s) for s in sigs):
                    # Allow webm/mp4 detection by 'ftyp' / 0x1A45DFA3 (Matroska)
                    if b"ftyp" not in head and head[:4] != b"\x1A\x45\xDF\xA3":
                        raise HTTPException(status_code=400, detail="Unrecognized or unsupported audio file signature.")
            else:
                # PNG (89 50 4E 47), JPEG (FF D8)
                if not (head.startswith(b"\x89PNG") or head.startswith(b"\xff\xd8")):
                    raise HTTPException(status_code=400, detail="Unrecognized image file signature.")
        except HTTPException:
            raise
        except Exception:
            # Non-fatal; continue (defense-in-depth only)
            try: f.file.seek(0)
            except Exception: pass

    def _copy_with_limit(src, dest_path: Path, max_bytes: int) -> int:
        """Stream copy to file enforcing a max size. Returns bytes written.
        Raises HTTPException 413 if exceeded.
        """
        total = 0
        try:
            with open(dest_path, "wb") as out:
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        # Stop writing and signal too large
                        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=f"File exceeds maximum allowed size of {max_bytes // (1024*1024)} MB.")
                    out.write(chunk)
        finally:
            try:
                src.close()
            except Exception:
                pass
        return total

    for i, file in enumerate(files):
        if not file.filename:
            continue
        
        # Log upload request received
        import logging
        log = logging.getLogger("api.media")
        log.info("[upload.request] Received upload request: category=%s, filename=%s, user_id=%s", 
                category.value, file.filename, current_user.id)

        # Validate type and extension early
        _validate_meta(file, category)

        original_filename = Path(file.filename).stem
        default_friendly_name = ' '.join(original_filename.split('_')).title()

        # --- FIX: Add uuid4 to filename to ensure uniqueness ---
        safe_orig = _sanitize_name(file.filename)
        safe_filename = f"{current_user.id.hex}_{uuid4().hex}_{safe_orig}"

        # Enforce per-category size limit
        max_bytes = CATEGORY_SIZE_LIMITS.get(category, 50 * MB)
        
        # **CRITICAL**: ALL files MUST be uploaded to GCS - no local storage fallback
        # This ensures files are accessible to worker servers and production environments
        # Use MEDIA_BUCKET (set in production) with fallback to GCS_BUCKET (for compatibility)
        gcs_bucket = os.getenv("MEDIA_BUCKET") or os.getenv("GCS_BUCKET") or "ppp-media-us-west1"
        if not gcs_bucket:
            raise HTTPException(status_code=500, detail="MEDIA_BUCKET or GCS_BUCKET environment variable not set - cloud storage is required")
        
        # Read file content into memory
        file_content = file.file.read(max_bytes)
        bytes_written = len(file_content)
        
        log.info("[upload.storage] Starting upload for %s: filename=%s, size=%d bytes, bucket=%s", 
                category.value, safe_filename, bytes_written, gcs_bucket)
        
        if bytes_written >= max_bytes:
            # Check if there's more data
            remaining = file.file.read(1)
            if remaining:
                raise HTTPException(status_code=413, detail=f"File exceeds maximum size of {max_bytes / MB:.1f} MB")
        
        try:
            # **CRITICAL**: Intermediate files (uploads) ALWAYS go to GCS, not R2
            # R2 is only for final files (assembled episodes)
            # This ensures worker servers can download intermediate files for processing
            from infrastructure import gcs
            # Determine storage key based on category
            if category == MediaCategory.main_content:
                # Main content goes to media_uploads for worker access
                storage_key = f"{current_user.id.hex}/media_uploads/{safe_filename}"
            else:
                # Other categories go to media/{category}
                storage_key = f"{current_user.id.hex}/media/{category.value}/{safe_filename}"
            
            log.info("[upload.storage] Uploading %s to GCS bucket %s, key: %s", 
                    category.value, gcs_bucket, storage_key)
            
            # Upload directly to GCS from memory - NO local file write, NO R2
            # CRITICAL: allow_fallback=False to ensure files are ALWAYS uploaded to GCS
            from io import BytesIO
            file_stream = BytesIO(file_content)
            final_content_type = file.content_type or ("audio/mpeg" if category != MediaCategory.podcast_cover and category != MediaCategory.episode_cover else "image/jpeg")
            storage_url = gcs.upload_fileobj(
                gcs_bucket,
                storage_key,
                file_stream,
                content_type=final_content_type,
                allow_fallback=False,  # Require GCS - no local fallback
                force_gcs=True  # Force GCS even if STORAGE_BACKEND=r2 (intermediate files must go to GCS)
            )
            
            # Store GCS URL - intermediate files always go to GCS (not R2)
            # URL format: gs://bucket/key
            if not storage_url:
                log.error("[upload.storage] CRITICAL: GCS upload returned None for %s - this should never happen with allow_fallback=False", category.value)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to upload {category.value} to GCS - upload returned None"
                )
            elif storage_url.startswith("gs://"):
                final_filename = storage_url
                log.info("[upload.storage] SUCCESS: %s uploaded to GCS: %s", category.value, storage_url)
                log.info("[upload.storage] MediaItem will be saved with filename='%s'", final_filename)
            else:
                # Upload returned a local path or invalid URL (should not happen with allow_fallback=False)
                log.error("[upload.storage] CRITICAL: GCS upload returned invalid URL: %s", storage_url)
                log.error("[upload.storage] Expected gs:// URL, but got: %s", storage_url)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to upload {category.value} to GCS - upload returned invalid URL: {storage_url}"
                )
        except HTTPException:
            raise
        except Exception as e:
            log.error("[upload.storage] CRITICAL: Failed to upload %s to GCS: %s", category.value, e, exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to upload {category.value} to GCS: {str(e)}"
            )

        friendly_name = names[i] if i < len(names) and names[i].strip() else default_friendly_name
        
        # Verify final_filename is a GCS URL before saving (intermediate files always go to GCS)
        if not final_filename.startswith("gs://"):
            log.error("[upload.storage] CRITICAL: final_filename is not a GCS URL: '%s'", final_filename)
            log.error("[upload.storage] Expected gs:// URL for intermediate file upload")
            raise HTTPException(
                status_code=500,
                detail=f"Internal error: filename is not a GCS URL. This indicates a bug in the upload process."
            )

        log.info("[upload.storage] Creating MediaItem with filename='%s' (GCS URL)", final_filename)
        media_item = MediaItem(
            filename=final_filename,
            friendly_name=friendly_name,
            content_type=final_content_type,
            filesize=bytes_written,
            user_id=current_user.id,
            category=category
        )
        session.add(media_item)
        created_items.append(media_item)
        log.info("[upload.storage] MediaItem created: id=%s, filename='%s'", media_item.id, media_item.filename)

        # Kick off immediate background transcription for main content uploads
        try:
            if category == MediaCategory.main_content:
                # Use Cloud Tasks to schedule transcription
                # Pass the GCS URL (final_filename) so transcription can download from GCS if needed
                from infrastructure.tasks_client import enqueue_http_task  # type: ignore
                task_result = enqueue_http_task("/api/tasks/transcribe", {
                    "filename": final_filename,  # Use GCS URL instead of just filename
                    "user_id": str(current_user.id)  # Pass user_id for tier-based routing
                })
                log.info("Transcription task enqueued for %s: %s", final_filename, task_result)
        except Exception as e:
            # Non-fatal; upload should still succeed
            # But log the error so we can diagnose why transcription isn't starting
            log.error("Failed to enqueue transcription task for %s: %s", final_filename, e, exc_info=True)

    # Commit - no local files to clean up since everything goes to GCS
    try:
        log.info("[upload.db] Committing %d MediaItem(s) to database", len(created_items))
        session.commit()
        # Verify the filenames were saved correctly
        for item in created_items:
            session.refresh(item)
            log.info("[upload.db] MediaItem saved: id=%s, filename='%s' (starts with gs://: %s)", 
                    item.id, item.filename, 
                    item.filename.startswith("gs://") if item.filename else False)
            if item.filename and not item.filename.startswith("gs://"):
                log.error("[upload.db] CRITICAL: MediaItem filename is not a GCS URL: '%s'", item.filename)
                log.error("[upload.db] Expected gs:// URL for intermediate file")
                log.error("[upload.db] This indicates the database save failed or was rolled back")
    except Exception as e:
        log.error("[upload.db] commit failed for %d items in category=%s: %s", len(created_items), category.value, e, exc_info=True)
        # Note: Files are already in GCS, so we can't easily clean them up here
        # They'll be orphaned but that's acceptable - GCS lifecycle policies can handle cleanup
        session.rollback()
        raise HTTPException(status_code=500, detail="Upload stored file(s), but database write failed. Please retry.")
    
    for item in created_items:
        session.refresh(item)
    
    return created_items

@router.get("/", response_model=List[MediaItem])
async def list_user_media(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Retrieve the current user's media library, filtering out main content and covers.

    Only return items in categories: intro, outro, music, sfx, commercial.
    """
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

@router.put("/{media_id}", response_model=MediaItem)
async def update_media_item_name(
    media_id: UUID,
    media_update: MediaItemUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Update the friendly name of a media item."""
    media_item = session.get(MediaItem, media_id)
    if not media_item or media_item.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Media item not found.")
    
    if media_update.friendly_name is not None:
        media_item.friendly_name = media_update.friendly_name
    if media_update.trigger_keyword is not None:
        # Normalize to lowercase simple token
        media_item.trigger_keyword = media_update.trigger_keyword.strip().lower() or None
    session.add(media_item)
    session.commit()
    session.refresh(media_item)
    return media_item

@router.delete("/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_media_item(
    media_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    # --- THIS IS THE FIX ---
    # Using a select statement to be more explicit, then fetching the single result.
    statement = select(MediaItem).where(MediaItem.id == media_id, MediaItem.user_id == current_user.id)
    media_item = session.exec(statement).one_or_none()

    if not media_item:
        raise HTTPException(status_code=404, detail="Media item not found or you don't have permission to delete it.")

    # Delete related records first to avoid foreign key violations
    try:
        # Delete any transcripts referencing this media item
        from ..models.transcription import MediaTranscript
        transcript_stmt = select(MediaTranscript).where(MediaTranscript.media_item_id == media_id)
        transcripts = session.exec(transcript_stmt).all()
        for transcript in transcripts:
            session.delete(transcript)
    except Exception:
        pass  # Table might not exist in some environments

    # Delete the file from disk
    file_path = MEDIA_DIR / media_item.filename
    if file_path.exists():
        file_path.unlink()
    
    # Now delete the media item
    session.delete(media_item)
    session.commit()
    
    return None

@router.get("/preview")
async def preview_media(
    id: Optional[str] = None,
    path: Optional[str] = None,
    resolve: bool = False,
    session: Session = Depends(get_session),
):
    """Return a temporary URL (or redirect) to preview a media item.
    
    NO AUTHENTICATION REQUIRED - Allows HTML5 <audio> element to play files.
    
    Args:
        id: MediaItem UUID to preview
        path: Direct gs:// path or local filename (alternative to id)
        resolve: If true, return JSON {url} instead of redirect
    """
    from fastapi.responses import JSONResponse, RedirectResponse
    import logging
    
    log = logging.getLogger("api.media.preview")
    
    item: Optional[MediaItem] = None
    if id:
        try:
            uid = UUID(id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid id")
        item = session.get(MediaItem, uid)
        if not item:
            raise HTTPException(status_code=404, detail="Media item not found")
        path = item.filename
        log.info(f"Preview request for media_id={id}, filename={path}")
    
    if not path:
        raise HTTPException(status_code=400, detail="Missing id or path")
    
    # Handle GCS URLs (build components, raw uploads, media library)
    if path.startswith("gs://"):
        p = path[5:]
        bucket, _, key = p.partition("/")
        if not bucket or not key:
            log.error(f"Invalid gs:// path format: {path}")
            raise HTTPException(status_code=400, detail="Invalid gs path")
        try:
            from infrastructure import gcs
            log.info(f"Generating signed URL for gs://{bucket}/{key}")
            url = gcs.make_signed_url(bucket, key, minutes=int(os.getenv("GCS_SIGNED_URL_TTL_MIN", "10")))
            log.info(f"Successfully generated signed URL: {url[:100]}...")
        except Exception as ex:
            log.error(f"Failed to generate signed URL: {ex}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to sign URL: {ex}")
        
        if resolve:
            return JSONResponse({"url": url})
        return RedirectResponse(url=url)
    
    # Handle R2 URLs (finished episode audio, images, transcripts)
    # R2 URLs are already public/signed, return directly
    elif path.startswith("https://") or path.startswith("http://"):
        log.info(f"[media/preview] R2 URL detected (finished product), returning directly: {path[:80]}...")
        if resolve:
            return JSONResponse({"url": path})
        return RedirectResponse(url=path)
    
    # Invalid path format - must be cloud storage
    log.error(f"Invalid media path (not cloud storage): {path}")
    raise HTTPException(
        status_code=400, 
        detail=f"Media file must be in cloud storage (gs:// or https://). Local files not supported. Path: {path[:50]}"
    )

# Schemas for main content endpoints
class MainContentItem(BaseModel):
    id: UUID
    filename: str
    friendly_name: Optional[str] = None
    created_at: Optional[str] = None
    expires_at: Optional[str] = None
    transcript_ready: bool = False
    intents: Dict = {}
    notify_pending: bool = False
    duration_seconds: Optional[float] = None

class PresignRequest(BaseModel):
    filename: str
    content_type: str = "audio/mpeg"

class PresignResponse(BaseModel):
    upload_url: str
    object_path: str
    headers: Dict[str, str] = {}

class RegisterUploadItem(BaseModel):
    object_path: str
    friendly_name: Optional[str] = None
    original_filename: Optional[str] = None
    content_type: Optional[str] = None
    size: Optional[int] = None

class RegisterRequest(BaseModel):
    uploads: List[RegisterUploadItem]
    notify_when_ready: bool = False
    notify_email: Optional[str] = None

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

def _compute_duration(words) -> Optional[float]:
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
    current_user: User = Depends(get_current_user)
):
    """Return main content uploads along with transcript/intents metadata.
    
    Excludes uploads that are already used in published/scheduled episodes to prevent
    duplicate episode creation from the same source file. Files remain available for
    7 days after publish for editing purposes but don't appear in new episode creation.
    """
    from api.models.podcast import Episode, EpisodeStatus
    
    # Get list of working_audio_name values from episodes that are published or scheduled
    # These files should not appear in the "Choose Processed Audio" list
    # Published = status is "published", Scheduled = status is "processed" with future publish_at
    try:
        published_episodes = session.exec(
            select(Episode).where(
                Episode.user_id == current_user.id,
                Episode.working_audio_name != None
            )
        ).all()
        
        in_use_files = set()
        for ep in published_episodes:
            # Filter ALL episodes using the file, not just published/scheduled
            # This prevents the same audio from being used in multiple episodes
            if ep.working_audio_name:
                in_use_files.add(str(ep.working_audio_name))
    except Exception:
        in_use_files = set()
    
    stmt = (
        select(MediaItem)
        .where(
            MediaItem.user_id == current_user.id,
            MediaItem.category == MediaCategory.main_content,
        )
        .order_by(_sa_text("created_at DESC"))
    )
    all_uploads = session.exec(stmt).all()
    
    # Filter out files that are already used in ANY episode
    uploads = [u for u in all_uploads if str(u.filename) not in in_use_files]

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
        transcript_path = _resolve_transcript_path(filename)
        
        # Use database transcript_ready field (transcripts now in GCS, not local files)
        ready = item.transcript_ready
        
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
                created_at=item.created_at.isoformat() if item.created_at else None,
                expires_at=item.expires_at.isoformat() if item.expires_at else None,
                transcript_ready=ready,
                intents=intents or {},
                notify_pending=pending,
                duration_seconds=duration,
            )
        )

    return results

@router.post("/upload/{category}/presign", response_model=PresignResponse)
async def presign_upload(
    category: MediaCategory,
    request: PresignRequest,
    current_user: User = Depends(get_current_user)
):
    """Generate a presigned URL for direct GCS upload.
    
    Uses signed URLs to bypass Cloud Run's 32MB request body limit.
    Files are uploaded directly to GCS, bypassing the API server.
    """
    import uuid
    from google.cloud import storage
    from datetime import timedelta
    
    # Generate unique object path in user's media directory
    # IMPORTANT: Match the path structure used by standard upload
    # main_content goes to media_uploads/, others go to media/{category}/
    user_id = current_user.id.hex
    file_ext = Path(request.filename).suffix.lower()
    unique_name = f"{uuid.uuid4().hex}{file_ext}"
    
    # Use same path structure as standard upload endpoint
    if category == MediaCategory.main_content:
        # Main content goes to media_uploads for worker access
        object_path = f"{user_id}/media_uploads/{unique_name}"
    else:
        # Other categories go to media/{category}
        object_path = f"{user_id}/media/{category.value}/{unique_name}"
    
    # Get GCS bucket name from environment
    # Use MEDIA_BUCKET (set in production) with fallback to GCS_BUCKET (for compatibility)
    gcs_bucket = os.getenv("MEDIA_BUCKET") or os.getenv("GCS_BUCKET") or "ppp-media-us-west1"
    
    import logging
    log = logging.getLogger("api.media")
    
    log.info(f"Generating upload URL for: gs://{gcs_bucket}/{object_path}")
    
    # Generate upload URL for direct GCS upload
    # Use the infrastructure helper which handles credential loading and signing
    try:
        log.info("Generating signed URL for resumable upload to GCS")
        
        # First, verify credentials can be loaded
        from infrastructure import gcs as gcs_module
        from infrastructure.gcs import _get_signing_credentials
        
        log.info("Checking if signing credentials are available...")
        signing_creds = _get_signing_credentials()
        
        if signing_creds:
            log.info("✅ Signing credentials loaded successfully")
            log.info(f"   Credentials type: {type(signing_creds).__name__}")
            if hasattr(signing_creds, 'service_account_email'):
                log.info(f"   Service account: {signing_creds.service_account_email}")
        else:
            log.warning("⚠️  No signing credentials available - will try IAM-based signing")
        
        # Use the infrastructure helper which tries multiple methods
        # For direct uploads, we'll use PUT method (simpler than resumable)
        # PUT signed URLs work for files up to ~5GB and are simpler for the frontend
        try:
            log.info("Generating signed URL for direct PUT upload...")
            upload_url = gcs_module._generate_signed_url(
                bucket_name=gcs_bucket,
                key=object_path,
                expires=timedelta(hours=1),
                method="PUT",  # PUT for direct upload (simpler than resumable)
                content_type=request.content_type,
            )
            
            if upload_url:
                log.info(f"✅ Successfully generated PUT upload URL for {object_path}")
                return PresignResponse(
                    upload_url=str(upload_url),
                    object_path=object_path,
                    headers={
                        "Content-Type": request.content_type
                    }
                )
            else:
                log.error("❌ _generate_signed_url returned None")
                raise ValueError("Signed URL generation returned None - check credentials and permissions")
                
        except RuntimeError as runtime_err:
            # IAM-based signing failed or no credentials
            error_msg = str(runtime_err).lower()
            log.error(f"❌ Signed URL generation failed: {runtime_err}", exc_info=True)
            
            # Check what credentials we have
            signer_key = os.getenv("GCS_SIGNER_KEY_JSON")
            if signer_key:
                log.error(f"   GCS_SIGNER_KEY_JSON is set (length: {len(signer_key)}, starts with: {signer_key[:50]}...)")
            else:
                log.error("   GCS_SIGNER_KEY_JSON is not set")
            
            if signing_creds:
                log.error(f"   But signing credentials were loaded: {type(signing_creds).__name__}")
            else:
                log.error("   And no signing credentials were loaded")
            
            raise HTTPException(
                status_code=501,
                detail="Direct upload not available (signing credentials required). "
                       "Files larger than 25MB may fail due to Cloud Run's 32MB limit. "
                       "Please contact support to enable direct uploads."
            )
        except Exception as url_err:
            # Any other error
            log.error(f"❌ Failed to generate upload URL: {url_err}", exc_info=True)
            raise
        
    except HTTPException as http_err:
        # Re-raise HTTP exceptions as-is (these are intentional)
        raise
    except Exception as url_err:
        # Catch ALL other errors - log them and return 501 so frontend falls back
        import traceback
        error_trace = traceback.format_exc()
        error_msg = str(url_err).lower()
        error_type = type(url_err).__name__
        
        # Log the full error for debugging
        log.error(
            f"Failed to generate upload URL for {object_path}: {error_type}: {url_err}\n"
            f"Traceback: {error_trace}"
        )
        
        # For ANY error, return 501 (Not Implemented) so frontend falls back to standard upload
        # This ensures uploads don't completely fail - they'll just use the standard endpoint
        # which works for files <25MB (or might work for larger files if Cloud Run allows it)
        raise HTTPException(
            status_code=501,
            detail=f"Direct upload temporarily unavailable. Falling back to standard upload. "
                   f"(Error: {error_type})"
        )

@router.post("/upload/{category}/register", response_model=List[MediaItem])
async def register_upload(
    category: MediaCategory,
    request: RegisterRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Register uploaded files in the database after direct GCS upload.
    
    Verifies the files exist in GCS and creates MediaItem records.
    """
    from infrastructure import gcs
    import logging
    
    log = logging.getLogger("api.media")
    # Use MEDIA_BUCKET (set in production) with fallback to GCS_BUCKET (for compatibility)
    gcs_bucket = os.getenv("MEDIA_BUCKET") or os.getenv("GCS_BUCKET") or "ppp-media-us-west1"
    created_items = []
    
    for upload_item in request.uploads:
        try:
            # CRITICAL: Verify object exists in GCS directly (not through storage abstraction)
            # Direct uploads always go to GCS, even when STORAGE_BACKEND=r2
            # We need to check GCS directly, not through the storage backend abstraction
            # Also handle eventual consistency with retries
            import time
            from google.cloud import storage
            
            client = storage.Client()
            bucket = client.bucket(gcs_bucket)
            blob = bucket.blob(upload_item.object_path)
            
            # Retry up to 3 times with delays for eventual consistency
            object_exists = False
            file_size = upload_item.size or 0
            max_retries = 3
            retry_delay = 1.0  # seconds
            
            for attempt in range(max_retries):
                try:
                    object_exists = blob.exists()
                    if object_exists:
                        # Get file size and metadata
                        blob.reload()
                        file_size = blob.size or upload_item.size or 0
                        log.info(f"✅ Verified upload in GCS: {upload_item.object_path} (size: {file_size} bytes, attempt {attempt + 1})")
                        break
                    else:
                        if attempt < max_retries - 1:
                            log.debug(f"Object not found in GCS (attempt {attempt + 1}/{max_retries}), retrying in {retry_delay}s...")
                            time.sleep(retry_delay)
                            retry_delay *= 2  # Exponential backoff
                        else:
                            log.warning(f"Object not found in GCS after {max_retries} attempts: {upload_item.object_path}")
                            raise HTTPException(
                                status_code=400,
                                detail=f"Upload verification failed: file not found at {upload_item.object_path} after {max_retries} attempts. The upload may still be processing - please wait a moment and try again."
                            )
                except HTTPException:
                    raise
                except Exception as verify_err:
                    if attempt < max_retries - 1:
                        log.warning(f"Failed to verify upload (attempt {attempt + 1}/{max_retries}): {verify_err}, retrying...")
                        time.sleep(retry_delay)
                        retry_delay *= 2
                    else:
                        log.error(f"Failed to verify upload in GCS after {max_retries} attempts: {verify_err}", exc_info=True)
                        raise HTTPException(
                            status_code=500,
                            detail=f"Failed to verify upload: {str(verify_err)}"
                        )
            
            # Create MediaItem record
            gcs_url = f"gs://{gcs_bucket}/{upload_item.object_path}"
            friendly_name = upload_item.friendly_name
            if not friendly_name:
                # Extract from original filename if provided
                if upload_item.original_filename:
                    friendly_name = Path(upload_item.original_filename).stem
                else:
                    friendly_name = "upload"
            
            media_item = MediaItem(
                filename=gcs_url,  # Store gs:// URL for persistence
                category=category,
                friendly_name=friendly_name,
                content_type=upload_item.content_type,
                filesize=file_size,  # MediaItem uses 'filesize' not 'size'
                user_id=current_user.id
            )
            session.add(media_item)
            session.commit()
            session.refresh(media_item)
            created_items.append(media_item)
            
            log.info(f"Registered direct upload: {media_item.id} -> {gcs_url}")
            
            # Trigger transcription if requested and category is main_content
            if request.notify_when_ready and category == MediaCategory.main_content:
                try:
                    # Schedule transcription - pass user_id so transcription service knows which API to call
                    # Pro users → Auphonic transcription API
                    # Free/Creator/Unlimited → AssemblyAI transcription API
                    from infrastructure.tasks_client import enqueue_http_task  # type: ignore
                    task_result = enqueue_http_task("/api/tasks/transcribe", {
                        "filename": gcs_url,
                        "user_id": str(current_user.id)
                    })
                    log.info(f"Transcription task enqueued for media_id={media_item.id}, user_id={current_user.id}, gcs_path={gcs_url}, task={task_result}")
                except Exception as trans_err:
                    log.error(f"Failed to enqueue transcription task for media_id={media_item.id}: {trans_err}", exc_info=True)
        
        except HTTPException:
            raise
        except Exception as e:
            log.exception(f"Failed to register upload: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to register upload: {str(e)}"
            )
    
    return created_items