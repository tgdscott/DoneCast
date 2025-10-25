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

        # Validate type and extension early
        _validate_meta(file, category)

        original_filename = Path(file.filename).stem
        default_friendly_name = ' '.join(original_filename.split('_')).title()

        # --- FIX: Add uuid4 to filename to ensure uniqueness ---
        safe_orig = _sanitize_name(file.filename)
        safe_filename = f"{current_user.id.hex}_{uuid4().hex}_{safe_orig}"
        file_path = MEDIA_DIR / safe_filename

    # Enforce per-category size limit during streaming copy
        max_bytes = CATEGORY_SIZE_LIMITS.get(category, 50 * MB)
        try:
            bytes_written = _copy_with_limit(file.file, file_path, max_bytes)
        except HTTPException:
            # Ensure partial file is removed
            try:
                if file_path.exists():
                    file_path.unlink()
            finally:
                pass
            raise
        except Exception:
            try:
                if file_path.exists():
                    file_path.unlink()
            finally:
                pass
            raise HTTPException(status_code=500, detail="Failed to save uploaded file.")
        
        # Optional: Convert large PCM formats (WAV/AIFF) to FLAC to save space
        final_content_type = (file.content_type or None)
        try:
            ext_lower = Path(safe_filename).suffix.lower()
            if ext_lower in {".wav", ".aif", ".aiff"}:
                flac_filename = Path(safe_filename).with_suffix(".flac").name
                flac_path = MEDIA_DIR / flac_filename
                # Attempt conversion via ffmpeg (must be available on PATH)
                # -y overwrite, lossless FLAC
                ffmpeg_bin = os.getenv("FFMPEG_BIN") or os.getenv("FFMPEG_PATH") or shutil.which("ffmpeg") or "ffmpeg"
                cmd = [
                    ffmpeg_bin, "-hide_banner", "-loglevel", "error",
                    "-y", "-i", str(file_path),
                    "-c:a", "flac",
                    str(flac_path),
                ]
                try:
                    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                    if proc.returncode == 0 and flac_path.exists():
                        # Replace stored file with FLAC
                        try:
                            file_path.unlink(missing_ok=True)
                        except Exception:
                            pass
                        file_path = flac_path
                        safe_filename = flac_filename
                        bytes_written = file_path.stat().st_size
                        final_content_type = "audio/flac"
                    else:
                        # Conversion failed; keep original
                        # Optionally log stderr via print to avoid adding logging deps here
                        try:
                            print("[media.upload] ffmpeg conversion failed:", proc.stderr)
                        except Exception:
                            pass
                except Exception as conv_err:
                    # ffmpeg unavailable or failed; keep original
                    try:
                        print("[media.upload] ffmpeg error:", conv_err)
                    except Exception:
                        pass
        except Exception:
            # Never fail the upload due to conversion issues
            pass

        friendly_name = names[i] if i < len(names) and names[i].strip() else default_friendly_name

        # Upload to GCS for persistence (intro/outro/music/sfx/commercial)
        gcs_bucket = os.getenv("GCS_BUCKET", "ppp-media-us-west1")
        final_filename = safe_filename  # Will be replaced with gs:// URL if GCS upload succeeds
        if gcs_bucket and category in (
            MediaCategory.intro,
            MediaCategory.outro,
            MediaCategory.music,
            MediaCategory.sfx,
            MediaCategory.commercial,
        ):
            try:
                from infrastructure import gcs
                # Use consistent path format: {user_id}/media/{category}/{filename}
                gcs_key = f"{current_user.id.hex}/media/{category.value}/{safe_filename}"
                with open(file_path, "rb") as f:
                    gcs_url = gcs.upload_fileobj(gcs_bucket, gcs_key, f, content_type=final_content_type or "audio/mpeg")
                
                # Verify GCS upload succeeded
                if gcs_url and gcs_url.startswith("gs://"):
                    final_filename = gcs_url
                    print(f"[media.upload] ✅ Uploaded {category.value} to GCS: {gcs_url}")
                else:
                    # GCS upload returned invalid URL - fail the upload
                    raise Exception(f"GCS upload returned invalid URL: {gcs_url}")
                    
            except Exception as e:
                # FAIL THE UPLOAD - don't silently fall back to /tmp
                print(f"[media.upload] ❌ FAILED to upload {category.value} to GCS: {e}")
                try:
                    file_path.unlink(missing_ok=True)
                except:
                    pass
                raise HTTPException(
                    status_code=500, 
                    detail=f"Failed to upload {category.value} to cloud storage: {str(e)}"
                )

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

        # Kick off immediate background transcription for main content uploads
        try:
            if category == MediaCategory.main_content:
                # Use Cloud Tasks to schedule transcription
                from infrastructure.tasks_client import enqueue_http_task  # type: ignore
                task_result = enqueue_http_task("/api/tasks/transcribe", {
                    "filename": safe_filename,
                    "user_id": str(current_user.id)  # Pass user_id for tier-based routing
                })
                import logging
                logging.getLogger("api.media").info(f"Transcription task enqueued for {safe_filename}: {task_result}")
        except Exception as e:
            # Non-fatal; upload should still succeed
            # But log the error so we can diagnose why transcription isn't starting
            import logging
            logging.getLogger("api.media").error(f"Failed to enqueue transcription task for {safe_filename}: {e}", exc_info=True)

    session.commit()
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
    current_user: User = Depends(get_current_user)
):
    """Return a temporary URL (or redirect) to preview a media item.
    
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
        if not item or item.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Not found")
        path = item.filename
        log.info(f"Preview request for media_id={id}, filename={path}")
    
    if not path:
        raise HTTPException(status_code=400, detail="Missing id or path")
    
    # Handle GCS URLs
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
    
    # Handle local files (development fallback)
    filename = path.lstrip("/\\")
    log.info(f"Checking local file: {filename}")
    try:
        media_root = MEDIA_DIR.resolve()
    except Exception:
        media_root = MEDIA_DIR
    
    try:
        candidate = (MEDIA_DIR / filename).resolve(strict=False)
        if not candidate.is_relative_to(media_root):
            log.error(f"Path traversal attempt: {filename}")
            raise HTTPException(status_code=403, detail="Path traversal not allowed")
        if not candidate.exists():
            log.error(f"File not found: {candidate}")
            raise HTTPException(status_code=404, detail=f"File not found: {filename}")
    except Exception as ex:
        log.error(f"Error resolving local file: {ex}")
        raise HTTPException(status_code=404, detail=str(ex))
    
    # For local files, return a relative API path
    rel = f"/api/media/files/{filename}"
    log.info(f"Returning local file path: {rel}")
    if resolve:
        return JSONResponse({"url": rel})
    return RedirectResponse(url=rel)

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
        ready = transcript_path.exists()
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
    
    Uses service account key from Secret Manager to sign URLs.
    This bypasses Cloud Run's 32MB request body limit.
    """
    import uuid
    from google.cloud import storage
    from datetime import timedelta
    
    # Generate unique object path in user's media directory
    user_id = current_user.id.hex
    file_ext = Path(request.filename).suffix.lower()
    unique_name = f"{uuid.uuid4().hex}{file_ext}"
    object_path = f"{user_id}/{category.value}/{unique_name}"
    
    # Get GCS bucket name from environment
    gcs_bucket = os.getenv("GCS_BUCKET", "ppp-media-us-west1")
    
    try:
        # Get signing credentials from Secret Manager
        from infrastructure.gcs import _get_signing_credentials
        credentials = _get_signing_credentials()
        
        if credentials is None:
            raise HTTPException(
                status_code=501,
                detail="Direct upload not available, use standard upload"
            )
        
        # Create storage client with signing credentials
        client = storage.Client(credentials=credentials)
        bucket = client.bucket(gcs_bucket)
        blob = bucket.blob(object_path)
        
        # Generate signed URL for PUT operation
        url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(hours=1),
            method="PUT",
            content_type=request.content_type,
        )
        
        return PresignResponse(
            upload_url=url,
            object_path=object_path,
            headers={"Content-Type": request.content_type}
        )
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.getLogger("api.media").error(f"Failed to generate signed URL: {e}", exc_info=True)
        # Fall back to 501 so frontend uses standard upload
        raise HTTPException(
            status_code=501,
            detail="Direct upload not available, use standard upload"
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
    gcs_bucket = os.getenv("GCS_BUCKET", "ppp-media-us-west1")
    created_items = []
    
    for upload_item in request.uploads:
        try:
            # Verify object exists in GCS
            object_exists = gcs.blob_exists(gcs_bucket, upload_item.object_path)
            if not object_exists:
                log.warning(f"Object not found in GCS: {upload_item.object_path}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Upload verification failed: file not found at {upload_item.object_path}"
                )
            
            # Use provided file size (we don't have a get_size function)
            file_size = upload_item.size or 0
            
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