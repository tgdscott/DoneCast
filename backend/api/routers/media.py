import shutil
import json
from uuid import uuid4
import subprocess
import os
from collections import defaultdict
from fastapi import APIRouter, HTTPException, status, Depends, UploadFile, File, Form
from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional, Dict
from uuid import UUID
from pathlib import Path
from sqlmodel import Session, select, func, col, desc
from sqlalchemy import text as _sa_text
from sqlalchemy import desc as _sa_desc
from sqlalchemy import exc as sa_exc
from sqlalchemy.orm import selectinload

from ..models.podcast import MediaItem, MediaCategory
from ..models.transcription import TranscriptionWatch
from ..models.user import User
from ..core.database import get_session
from ..core.paths import TRANSCRIPTS_DIR
from api.routers.auth import get_current_user
from api.routers.ai_suggestions import _gather_user_sfx_entries
from api.services.audio.transcript_io import load_transcript_json
from api.services.intent_detection import analyze_intents, get_user_commands
from infrastructure import gcs

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
    friendly_names: Optional[str] = Form(None),
    use_auphonic: Optional[bool] = Form(None),  # Deprecated: ignored. Routing via decision helper + ALWAYS_USE_ADVANCED_PROCESSING setting
    guest_ids: Optional[str] = Form(None) # JSON string of guest IDs
):
    """Upload one or more media files with optional friendly names.
    
    ROUTING NOTE: The 'use_auphonic' form parameter is deprecated and ignored.
    Auphonic routing is now determined entirely by the decision helper, which
    considers: audio quality metrics, user tier, and ALWAYS_USE_ADVANCED_PROCESSING setting.
    """
    created_items = []
    names = json.loads(friendly_names) if friendly_names else []
    guests_list = json.loads(guest_ids) if guest_ids else []

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
        
        # Robustly handle current_user.id (could be UUID object or string)
        user_id_hex = current_user.id.hex if hasattr(current_user.id, "hex") else str(current_user.id).replace("-", "")
        safe_filename = f"{user_id_hex}_{uuid4().hex}_{safe_orig}"

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
            from io import BytesIO
            file_stream = BytesIO(file_content)
            final_content_type = file.content_type or ("audio/mpeg" if category != MediaCategory.podcast_cover and category != MediaCategory.episode_cover else "image/jpeg")
            
            # **CRITICAL**: Episode covers are FINAL ASSETS, not intermediate files
            # They should go to R2 (permanent storage) like assembled episodes
            # This ensures covers work permanently without expiration
            if category == MediaCategory.episode_cover:
                from infrastructure import r2 as r2_module
                r2_bucket = os.getenv("R2_BUCKET", "ppp-media").strip()
                # Use structure: covers/episode/{user_id}/{filename}
                # When assigned to a specific episode, it can be migrated to {user_id}/episodes/{episode_id}/cover/{filename}
                # For now, this generic path works and ensures covers are in R2 (permanent storage)
                storage_key = f"covers/episode/{current_user.id.hex}/{safe_filename}"
                
                log.info("[upload.storage] Uploading episode_cover to R2 bucket %s, key: %s", r2_bucket, storage_key)
                
                r2_url = r2_module.upload_bytes(r2_bucket, storage_key, file_content, content_type=final_content_type)
                if not r2_url:
                    log.error("[upload.storage] CRITICAL: R2 upload returned None for episode_cover")
                    raise HTTPException(
                        status_code=500,
                        detail="Failed to upload episode cover to R2 - upload returned None"
                    )
                final_filename = r2_url
                log.info("[upload.storage] SUCCESS: episode_cover uploaded to R2: %s", r2_url)
                log.info("[upload.storage] MediaItem will be saved with filename='%s'", final_filename)
            else:
                # **CRITICAL**: Intermediate files (uploads) ALWAYS go to GCS, not R2
                # R2 is only for final files (assembled episodes and episode covers)
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
        
        # Verify final_filename is valid (GCS URL for intermediate files, R2 URL for episode covers)
        if category == MediaCategory.episode_cover:
            # Episode covers go to R2 - verify it's an R2 URL
            if not (final_filename.startswith("https://") and ".r2.cloudflarestorage.com" in final_filename):
                log.error("[upload.storage] CRITICAL: final_filename is not an R2 URL: '%s'", final_filename)
                raise HTTPException(
                    status_code=500,
                    detail="Internal error: episode cover filename is not an R2 URL. This indicates a bug in the upload process."
                )
        else:
            # Intermediate files go to GCS - verify it's a GCS URL
            if not final_filename.startswith("gs://"):
                log.error("[upload.storage] CRITICAL: final_filename is not a GCS URL: '%s'", final_filename)
                log.error("[upload.storage] Expected gs:// URL for intermediate file upload")
                raise HTTPException(
                    status_code=500,
                    detail=f"Internal error: filename is not a GCS URL. This indicates a bug in the upload process."
                )

        # For main_content uploads, validate storage limits and set tier-based expiration
        expires_at = None
        if category == MediaCategory.main_content:
            # Get user's tier
            user_tier = getattr(current_user, "tier", "starter") or "starter"
            # Normalize "free" to "starter"
            if user_tier.lower() == "free":
                user_tier = "starter"
            
            # Validate storage limits
            try:
                from api.services.storage.validation import check_storage_limits
                from api.services.episodes.assembler import _estimate_audio_seconds
                
                # Try to estimate duration from the uploaded file
                # Note: This may not always work for GCS files, but we'll try
                estimated_seconds = None
                try:
                    # Try to estimate from the GCS file
                    estimated_seconds = _estimate_audio_seconds(final_filename)
                except Exception:
                    # If estimation fails, we'll allow the upload but log a warning
                    # The cleanup task will handle enforcement later
                    log.warning("[storage] Could not estimate audio duration for %s, allowing upload", final_filename)
                
                # Check storage limits (will skip if estimation failed)
                if estimated_seconds is not None:
                    allowed, error_msg = check_storage_limits(
                        session,
                        str(current_user.id),
                        user_tier,
                        new_file_duration_seconds=estimated_seconds
                    )
                    if not allowed:
                        # Delete the uploaded file from GCS
                        try:
                            from infrastructure.gcs import delete_blob
                            if final_filename.startswith("gs://"):
                                bucket_key = final_filename[5:]  # Remove "gs://" prefix
                                bucket, _, key = bucket_key.partition("/")
                                if bucket and key:
                                    delete_blob(bucket, key)
                                    log.info("[storage] Deleted uploaded file due to storage limit: %s", final_filename)
                        except Exception as e:
                            log.warning("[storage] Failed to delete uploaded file after storage limit error: %s", e)
                        
                        raise HTTPException(status_code=403, detail=error_msg or "Storage limit exceeded")
                
                # Set tier-based expiration
                try:
                    from api.startup_tasks import _compute_pt_expiry
                    from datetime import datetime
                    now_utc = datetime.utcnow()
                    expires_at = _compute_pt_expiry(now_utc, tier=user_tier)
                    log.info("[storage] Set expiration for %s: tier=%s, expires_at=%s", final_filename, user_tier, expires_at)
                except Exception as e:
                    log.warning("[storage] Failed to set expiration date: %s", e, exc_info=True)
                    # Don't fail upload if expiration calculation fails
            except HTTPException:
                raise
            except Exception as e:
                log.warning("[storage] Storage validation error (non-fatal): %s", e, exc_info=True)
                # Don't fail upload if validation fails - we'll enforce limits in cleanup
        
        storage_type = "R2 URL" if category == MediaCategory.episode_cover else "GCS URL"
        log.info("[upload.storage] Creating MediaItem with filename='%s' (%s)", final_filename, storage_type)
        media_item = MediaItem(
            filename=final_filename,
            friendly_name=friendly_name,
            content_type=final_content_type,
            filesize=bytes_written,
            user_id=current_user.id,
            category=category,
            expires_at=expires_at,
            use_auphonic=False,  # Will be set by decision helper below
            guest_ids=guests_list if category == MediaCategory.main_content else None
        )
        session.add(media_item)
        created_items.append(media_item)
        log.info("[upload.storage] MediaItem created: id=%s, filename='%s'", media_item.id, media_item.filename)

        # Kick off immediate background transcription for main content uploads
        try:
            if category == MediaCategory.main_content:
                # --- DEDUPLICATION START ---
                # Before we do expensive analysis and enqueue task, check if this is a re-upload
                # of an existing file that already has a transcript.
                is_deduplicated = False
                dedup_source = None
                
                try:
                    # We need the stem of the NEW filename we just generated
                    new_stem = Path(final_filename).stem
                    
                    is_deduplicated, dedup_source = _attempt_deduplication(
                        session=session,
                        user_id=current_user.id,
                        filesize=bytes_written,
                        friendly_name=friendly_name,
                        original_stem=original_filename, # From earlier in function
                        new_stem=new_stem,
                        bucket_name=gcs_bucket
                    )
                    
                    if is_deduplicated and dedup_source:
                        log.info("[upload.dedupe] SUCCESS: Reusing transcript from MediaItem %s for new upload %s", 
                                    dedup_source.id, media_item.id)
                        
                        # Copy metadata
                        media_item.transcript_ready = True
                        media_item.audio_quality_metrics_json = dedup_source.audio_quality_metrics_json
                        media_item.audio_quality_label = dedup_source.audio_quality_label
                        media_item.audio_processing_decision_json = dedup_source.audio_processing_decision_json
                        media_item.use_auphonic = dedup_source.use_auphonic
                        media_item.auphonic_processed = dedup_source.auphonic_processed
                        media_item.auphonic_cleaned_audio_url = dedup_source.auphonic_cleaned_audio_url
                        # Note: We don't copy guest_ids unless we want to assume same speakers? 
                        # Maybe safe to leave as user-provided list.
                        
                        session.add(media_item)
                        session.flush() # Persist changes
                        
                        # Skip the rest of the analysis/task enqueue
                        # We must manual commit here since we are 'continuing' the loop which might
                        # mean skipping the end-of-loop logic if it existed, but here we are inside the loop
                        # and the commit happens at the end of the loop? 
                        # actually commit happens after the loop for all items.
                        # so 'continue' goes to next file. 
                        # Logic check: 'created_items' has the item. The commit is at line ~473.
                        # So 'continue' is safe.
                        continue 
                except Exception as dedup_err:
                    log.warning("[upload.dedupe] Failed to deduplicate: %s", dedup_err)
                    # Continue to normal processing
                # --- DEDUPLICATION END ---

                # Analyze audio immediately after upload and before transcription routing
                try:
                    from api.services.audio.quality import analyze_audio_file
                    from api.services.auphonic_helper import decide_audio_processing
                    import json as _json

                    metrics = analyze_audio_file(final_filename)
                    audio_label = metrics.get("quality_label") if isinstance(metrics, dict) else None

                    # Decide routing based on quality, tier, and operator setting
                    # NOTE: use_auphonic form parameter is ignored here; decision is authoritative
                    try:
                        from api.services.trial_service import get_effective_tier
                        user_tier = get_effective_tier(current_user)
                    except Exception:
                        user_tier = None

                    # Get user's threshold preference (defensive - column may not exist yet during migration)
                    try:
                        user_threshold = getattr(current_user, 'audio_processing_threshold_label', None)
                    except Exception:
                        # Column doesn't exist yet - migration pending
                        user_threshold = None
                    
                    decision = decide_audio_processing(
                        audio_quality_label=audio_label,
                        current_user_tier=user_tier,
                        media_item_override_use_auphonic=None,  # Never override; let decision matrix + tier + config decide
                        user_quality_threshold=user_threshold,
                    )

                    final_use_auphonic = bool(decision.get("use_auphonic", False))
                    
                    # Persist metrics and decision in new dedicated columns (durable, queryable)
                    # Defensive: columns may not exist yet during migration
                    # IMPORTANT: PostgreSQL JSONB columns expect Python dicts, not JSON strings
                    try:
                        media_item.audio_quality_metrics_json = metrics  # Pass dict directly, not JSON string
                        media_item.audio_quality_label = audio_label
                        media_item.audio_processing_decision_json = decision  # Pass dict directly, not JSON string
                        media_item.use_auphonic = final_use_auphonic
                        log.info("[upload.quality] MediaItem %s: label=%s, use_auphonic=%s, reason=%s", 
                                 media_item.id, audio_label, final_use_auphonic, decision.get("reason"))
                    except (AttributeError, Exception) as persist_err:
                        # Columns don't exist yet - migration pending
                        # Still set use_auphonic via legacy method if possible
                        log.warning("[upload.quality] Could not persist quality metrics (migration pending): %s", persist_err)
                        try:
                            media_item.use_auphonic = final_use_auphonic
                        except Exception:
                            pass

                    # Use Cloud Tasks to schedule transcription and include analysis+decision
                    from infrastructure.tasks_client import enqueue_http_task  # type: ignore
                    task_payload = {
                        "filename": final_filename,
                        "user_id": str(current_user.id),
                        "guest_ids": guests_list,
                        "audio_quality_label": audio_label,
                        "audio_quality_metrics": metrics if metrics else {},  # Ensure dict for JSON serialization
                        "use_auphonic": final_use_auphonic,
                    }
                    task_result = enqueue_http_task("/api/tasks/transcribe", task_payload)
                    log.info("[upload.transcribe] Task enqueued for %s: job_id=%s (use_auphonic=%s, label=%s, reason=%s)", 
                             final_filename, task_result, final_use_auphonic, audio_label, decision.get("reason"))
                except Exception as analysis_err:
                    # If analysis or decision fails, fall back to original behavior (enqueue without metrics)
                    log.warning("[upload.quality] Analysis/decision failed for %s: %s", final_filename, analysis_err, exc_info=True)
                    from infrastructure.tasks_client import enqueue_http_task  # type: ignore
                    task_result = enqueue_http_task("/api/tasks/transcribe", {
                        "filename": final_filename,
                        "user_id": str(current_user.id),
                        "guest_ids": guests_list
                    })
                    log.info("[upload.transcribe] Task enqueued (fallback, no analysis): %s", task_result)
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
            is_gcs = item.filename.startswith("gs://") if item.filename else False
            is_r2 = item.filename.startswith("https://") and ".r2.cloudflarestorage.com" in item.filename if item.filename else False
            log.info("[upload.db] MediaItem saved: id=%s, filename='%s' (starts with gs://: %s, is R2: %s)", 
                    item.id, item.filename, is_gcs, is_r2)
            # Episode covers go to R2, other files go to GCS
            if item.category == MediaCategory.episode_cover:
                if item.filename and not is_r2:
                    log.error("[upload.db] CRITICAL: Episode cover MediaItem filename is not an R2 URL: '%s'", item.filename)
                    log.error("[upload.db] Expected R2 URL (https://...r2.cloudflarestorage.com/...) for episode cover")
                    log.error("[upload.db] This indicates the database save failed or was rolled back")
            else:
                if item.filename and not is_gcs:
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
    
    # Send completion emails for main_content uploads with quality assessment
    if category == MediaCategory.main_content and current_user.email:
        try:
            from api.services.upload_completion_mailer import send_upload_success_email
            
            for item in created_items:
                # Extract quality info from persistent columns
                audio_label = item.audio_quality_label
                processing_decision = None
                if item.audio_processing_decision_json:
                    processing_decision = item.audio_processing_decision_json
                
                processing_type = "advanced" if item.use_auphonic else "standard"
                
                # Extract metrics if available
                audio_metrics = None
                if item.audio_quality_metrics_json:
                    audio_metrics = item.audio_quality_metrics_json
                
                # Send email (non-blocking; don't fail upload if email fails)
                try:
                    email_sent = send_upload_success_email(
                        user=current_user,
                        media_item=item,
                        quality_label=audio_label,
                        processing_type=processing_type,
                        audio_quality_metrics=audio_metrics,
                    )
                    if email_sent:
                        log.info(
                            "[upload.email] Success notification sent: user=%s media_id=%s quality=%s",
                            current_user.email,
                            item.id,
                            audio_label,
                        )
                    else:
                        log.warning(
                            "[upload.email] Success notification rejected by mailer: user=%s media_id=%s",
                            current_user.email,
                            item.id,
                        )
                except Exception as email_err:
                    log.exception(
                        "[upload.email] Exception sending success email: user=%s media_id=%s error=%s",
                        current_user.email,
                        item.id,
                        email_err,
                    )
        except Exception as e:
            log.error("[upload.email] Failed to send completion emails: %s", e, exc_info=True)
            # Don't fail the upload - email is non-critical
    
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
    """Delete a media item and its associated files from storage."""
    import logging
    log = logging.getLogger("api.media.delete")
    
    # Using a select statement to be more explicit, then fetching the single result.
    statement = select(MediaItem).where(MediaItem.id == media_id, MediaItem.user_id == current_user.id)
    media_item = session.exec(statement).one_or_none()

    if not media_item:
        raise HTTPException(status_code=404, detail="Media item not found or you don't have permission to delete it.")

    filename = str(media_item.filename or "").strip()
    log.info(f"[delete] Deleting media item {media_id}, filename: {filename}")

    # Delete related records first to avoid foreign key violations
    # CRITICAL: Delete transcripts before media item to avoid foreign key constraint violations
    # Use direct SQL DELETE for reliability and to ensure all transcripts are deleted atomically
    try:
        from ..models.transcription import MediaTranscript
        
        # First, check how many transcripts exist (for logging)
        transcript_stmt = select(MediaTranscript).where(MediaTranscript.media_item_id == media_id)
        transcripts = session.exec(transcript_stmt).all()
        transcript_count = len(transcripts)
        
        if transcript_count > 0:
            log.info(f"[delete] Found {transcript_count} transcript(s) to delete for media item {media_id}")
            transcript_ids = [str(t.id) for t in transcripts]
            log.info(f"[delete] Transcript IDs to delete: {', '.join(transcript_ids)}")
            
            # Use raw SQL DELETE to ensure all transcripts are deleted atomically
            # This is more reliable than ORM deletes and ensures the deletion happens immediately
            # Get the table name from the model (SQLModel converts CamelCase to snake_case)
            table_name = MediaTranscript.__tablename__
            delete_sql = _sa_text(
                f"DELETE FROM {table_name} WHERE media_item_id = :media_item_id"
            )
            result = session.execute(delete_sql, {"media_item_id": str(media_id)})
            deleted_count = result.rowcount
            
            # Flush to ensure the deletion is executed in the database
            session.flush()
            log.info(f"[delete] Successfully deleted {deleted_count} transcript(s) for media item {media_id}")
            
            if deleted_count != transcript_count:
                log.warning(
                    f"[delete] Mismatch: found {transcript_count} transcript(s) but deleted {deleted_count}. "
                    f"This might indicate a race condition or duplicate transcripts."
                )
        else:
            log.debug(f"[delete] No transcripts found for media item {media_id}")
    except Exception as transcript_err:
        # Table might not exist in some environments, or deletion failed
        log.error(f"[delete] Error deleting transcripts: {transcript_err}", exc_info=True)
        # Rollback and re-raise - we can't proceed if transcript deletion fails
        # as it will cause a foreign key violation
        session.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete related transcripts: {str(transcript_err)}"
        )

    # Delete the file from storage (GCS or local)
    try:
        if filename.startswith("gs://"):
            # Delete from GCS - media files are always stored in GCS, even if STORAGE_BACKEND=r2
            log.info(f"[delete] Deleting from GCS: {filename}")
            try:
                # Use GCS client directly (like orchestrator cleanup) to ensure we can delete
                # even if STORAGE_BACKEND=r2, since media files are always in GCS
                from google.cloud import storage
                from infrastructure.gcs import _get_gcs_client
                
                path_part = filename[5:]  # Remove "gs://" prefix
                bucket_name, _, key = path_part.partition('/')
                if bucket_name and key:
                    # Use cached client if available, otherwise create one
                    client = _get_gcs_client(force=True)
                    if not client:
                        client = storage.Client()
                    bucket = client.bucket(bucket_name)
                    blob = bucket.blob(key)
                    
                    # Check if blob exists before deleting
                    if blob.exists():
                        blob.delete()
                        log.info(f"[delete] Successfully deleted GCS object: gs://{bucket_name}/{key}")
                    else:
                        log.warning(f"[delete] GCS object does not exist: {filename} (may have been already deleted)")
                else:
                    log.warning(f"[delete] Invalid GCS URL format: {filename}")
            except Exception as gcs_err:
                # Don't block DB delete if GCS cleanup fails (file might already be deleted)
                log.warning(f"[delete] Failed to delete GCS object {filename}: {gcs_err}", exc_info=True)
        elif filename.startswith("https://") or filename.startswith("http://"):
            # R2 or other HTTP URLs - log but don't try to delete (these are final products)
            log.info(f"[delete] Skipping deletion of R2/HTTP URL (final product): {filename}")
        else:
            # Fallback for local files (development only)
            log.info(f"[delete] Deleting local file: {filename}")
            file_path = MEDIA_DIR / filename
            if file_path.exists():
                try:
                    file_path.unlink()
                    log.info(f"[delete] Successfully deleted local file: {file_path}")
                except Exception as local_err:
                    log.warning(f"[delete] Failed to delete local file {file_path}: {local_err}", exc_info=True)
    except Exception as storage_err:
        # Don't block DB delete if storage cleanup fails
        log.warning(f"[delete] Error during storage cleanup: {storage_err}", exc_info=True)
    
    # Now delete the media item from database
    # Transcripts have already been deleted and flushed, so this should succeed
    try:
        session.delete(media_item)
        session.commit()
        log.info(f"[delete] Successfully deleted media item {media_id} from database")
    except Exception as db_err:
        log.error(f"[delete] Failed to delete media item from database: {db_err}", exc_info=True)
        session.rollback()
        # Check if it's a foreign key violation - this shouldn't happen if we flushed transcripts
        error_str = str(db_err).lower()
        if "foreign key" in error_str or "foreignkey" in error_str:
            raise HTTPException(
                status_code=500, 
                detail=f"Failed to delete media item: foreign key constraint violation. This may indicate there are still references to this media item. Please contact support."
            )
        raise HTTPException(status_code=500, detail=f"Failed to delete media item: {str(db_err)}")
    
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
    
    # Handle GCS URLs (gs://bucket/key)
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
            return JSONResponse({"url": url, "path": url})
        return RedirectResponse(url=url)
    
    # Handle R2 paths (r2://bucket/key) - convert to signed URL
    elif path.startswith("r2://"):
        p = path[5:]
        bucket, _, key = p.partition("/")
        if not bucket or not key:
            log.error(f"Invalid r2:// path format: {path}")
            raise HTTPException(status_code=400, detail="Invalid r2 path")
        try:
            from infrastructure import r2
            log.info(f"Generating signed URL for r2://{bucket}/{key}")
            url = r2.generate_signed_url(bucket, key, expiration=600)  # 10 minutes
            if not url:
                raise RuntimeError("R2 signed URL generation returned None")
            log.info(f"Successfully generated R2 signed URL: {url[:100]}...")
        except Exception as ex:
            log.error(f"Failed to generate R2 signed URL: {ex}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to sign R2 URL: {ex}")
        
        if resolve:
            return JSONResponse({"url": url, "path": url})
        return RedirectResponse(url=url)
    
    # Handle HTTP/HTTPS URLs (already public/signed, return directly)
    elif path.startswith("https://") or path.startswith("http://"):
        log.info(f"[media/preview] HTTP(S) URL detected, returning directly: {path[:80]}...")
        if resolve:
            return JSONResponse({"url": path, "path": path})
        return RedirectResponse(url=path)
    
    # Invalid path format - must be cloud storage
    log.error(f"Invalid media path (not cloud storage): {path}")
    raise HTTPException(
        status_code=400, 
        detail=f"Media file must be in cloud storage (gs://, r2://, or https://). Local files not supported. Path: {path[:50]}"
    )

# Schemas for main content endpoints
class MainContentItem(BaseModel):
    id: UUID
    filename: str
    friendly_name: Optional[str] = None
    created_at: Optional[str] = None
    expires_at: Optional[str] = None
    transcript_ready: bool = False
    transcript_error: Optional[str] = None  # Error message if transcript recovery failed
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
    use_auphonic: Optional[bool] = Field(default=False, description="True if Auphonic transcription was requested (checkbox on upload)")
    guest_ids: Optional[List[str]] = Field(default=None, description="List of guest IDs associated with this upload")
    guest_ids: Optional[List[str]] = Field(default=None, description="List of guest IDs associated with this upload")

class RegisterRequest(BaseModel):
    uploads: List[RegisterUploadItem]
    notify_when_ready: bool = False
    notify_email: Optional[str] = None
    guest_ids: Optional[List[str]] = None # Backward compatibility if passed at top level

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
        
        # Backfill expires_at if missing (for existing files uploaded before tier-based expiration)
        expires_at = item.expires_at
        if not expires_at and item.created_at:
            try:
                from api.startup_tasks import _compute_pt_expiry
                user_tier = getattr(current_user, "tier", "starter") or "starter"
                if user_tier.lower() == "free":
                    user_tier = "starter"
                expires_at = _compute_pt_expiry(item.created_at, tier=user_tier)
                # Optionally update the database (but don't block the response)
                try:
                    item.expires_at = expires_at
                    session.add(item)
                    session.commit()
                except Exception:
                    session.rollback()
                    # Non-fatal - we'll calculate it on-the-fly
            except Exception:
                # If calculation fails, expires_at remains None
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
                expires_at=expires_at.isoformat() if expires_at else None,
                transcript_ready=ready,
                transcript_error=item.transcription_error,
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
    # Handle both UUID objects and string IDs
    user_id = str(current_user.id).replace('-', '') if isinstance(current_user.id, str) else current_user.id.hex
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
    
    # Create GCS client once and reuse for all upload items (performance optimization)
    import time
    from google.cloud import storage
    from infrastructure.gcs import _get_gcs_client
    
    # Use cached client if available, otherwise create one
    client = _get_gcs_client(force=True)
    if not client:
        # Fallback: create client directly if cache is empty
        client = storage.Client()
    
    bucket = client.bucket(gcs_bucket)
    
    for upload_item in request.uploads:
        try:
            # CRITICAL: Verify object exists in GCS directly (not through storage abstraction)
            # Direct uploads always go to GCS, even when STORAGE_BACKEND=r2
            # We need to check GCS directly, not through the storage backend abstraction
            # Also handle eventual consistency with retries
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
                user_id=current_user.id,
                use_auphonic=bool(upload_item.use_auphonic or False),  # CRITICAL: Sole source of truth for transcription routing
                guest_ids=upload_item.guest_ids or request.guest_ids  # Store guest IDs
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
                        "user_id": str(current_user.id),
                        "guest_ids": media_item.guest_ids # Pass guest IDs to transcription task
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

# Interview/Multi-track endpoints
class MergeTracksRequest(BaseModel):
    track_paths: List[str]
    gains_db: Optional[List[float]] = None
    sync_offsets_ms: Optional[List[int]] = None
    friendly_name: Optional[str] = None

class MergeTracksResponse(BaseModel):
    merged_filename: str
    duration_ms: int
    tracks_merged: int

@router.post("/merge-interview-tracks", response_model=MergeTracksResponse, status_code=status.HTTP_201_CREATED)
async def merge_interview_tracks_endpoint(
    request: MergeTracksRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Merge multiple audio tracks (e.g., from Zoom separate recordings) into a single file.
    
    Downloads tracks from GCS if needed, merges them, uploads result, and creates MediaItem.
    """
    import tempfile
    import uuid
    from pathlib import Path
    from api.services.audio.interview_merger import InterviewMerger
    from infrastructure import gcs
    
    log = logging.getLogger("api.media.merge")
    
    if not request.track_paths or len(request.track_paths) < 2:
        raise HTTPException(status_code=400, detail="At least 2 tracks are required for merging")
    
    log.info(f"[merge] Merging {len(request.track_paths)} tracks for user {current_user.id}")
    
    # Create temp directory for processing
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        downloaded_tracks = []
        
        try:
            # Download tracks from GCS if needed
            for i, track_path in enumerate(request.track_paths):
                local_path = temp_path / f"track_{i}.mp3"
                
                if track_path.startswith("gs://"):
                    # Download from GCS
                    bucket_key = track_path[5:]  # Remove "gs://"
                    bucket, _, key = bucket_key.partition("/")
                    
                    gcs_bucket = os.getenv("MEDIA_BUCKET") or os.getenv("GCS_BUCKET") or "ppp-media-us-west1"
                    if bucket != gcs_bucket:
                        # Track is in different bucket, download it
                        from google.cloud import storage
                        client = storage.Client()
                        source_bucket = client.bucket(bucket)
                        blob = source_bucket.blob(key)
                        blob.download_to_filename(str(local_path))
                    else:
                        # Same bucket, use GCS helper
                        from infrastructure.gcs import download_bytes
                        audio_bytes = download_bytes(bucket, key)
                        if audio_bytes:
                            with open(local_path, "wb") as f:
                                f.write(audio_bytes)
                        else:
                            raise HTTPException(status_code=404, detail=f"Failed to download track from GCS: {track_path}")
                elif Path(track_path).exists():
                    # Local file (for development/testing)
                    import shutil
                    shutil.copy2(track_path, local_path)
                else:
                    raise HTTPException(status_code=400, detail=f"Track not found: {track_path}")
                
                downloaded_tracks.append(str(local_path))
            
            # Merge tracks
            merger = InterviewMerger()
            output_filename = request.friendly_name or f"merged_interview_{uuid.uuid4().hex[:8]}.mp3"
            merged_path = temp_path / output_filename
            
            tracks_info = [
                {"path": path, "gain_db": request.gains_db[i] if request.gains_db and i < len(request.gains_db) else 0.0}
                for i, path in enumerate(downloaded_tracks)
            ]
            
            merge_result = merger.merge_tracks(
                tracks=tracks_info,
                output_path=merged_path,
                sync_offsets_ms=request.sync_offsets_ms,
            )
            
            # Upload merged file to GCS
            gcs_bucket = os.getenv("MEDIA_BUCKET") or os.getenv("GCS_BUCKET") or "ppp-media-us-west1"
            user_id = current_user.id.hex
            storage_key = f"{user_id}/media_uploads/{uuid.uuid4().hex}_{output_filename}"
            
            with open(merged_path, "rb") as f:
                storage_url = gcs.upload_fileobj(
                    gcs_bucket,
                    storage_key,
                    f,
                    content_type="audio/mpeg",
                    allow_fallback=False,
                    force_gcs=True,
                )
            
            if not storage_url or not storage_url.startswith("gs://"):
                raise HTTPException(status_code=500, detail="Failed to upload merged file to GCS")
            
            # Create MediaItem
            media_item = MediaItem(
                filename=storage_url,
                friendly_name=request.friendly_name or "Merged Interview",
                content_type="audio/mpeg",
                filesize=merged_path.stat().st_size,
                user_id=current_user.id,
                category=MediaCategory.main_content,
                use_auphonic=False  # Merged files default to AssemblyAI (no checkbox on merge)
            )
            session.add(media_item)
            session.commit()
            session.refresh(media_item)
            
            # Trigger transcription with multichannel support if multiple tracks
            try:
                from infrastructure.tasks_client import enqueue_http_task
                enqueue_http_task("/api/tasks/transcribe", {
                    "filename": storage_url,
                    "user_id": str(current_user.id),
                    "multichannel": len(request.track_paths) > 1,  # Enable multichannel for merged tracks
                })
            except Exception as e:
                log.warning(f"[merge] Failed to enqueue transcription: {e}", exc_info=True)
            
            return MergeTracksResponse(
                merged_filename=storage_url,
                duration_ms=merge_result["duration_ms"],
                tracks_merged=len(request.track_paths),
            )
        
        except HTTPException:
            raise
        except Exception as e:
            log.error(f"[merge] Failed to merge tracks: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to merge tracks: {str(e)}")

@router.get("/zoom-recordings", response_model=List[Dict])
async def list_zoom_recordings(
    current_user: User = Depends(get_current_user),
    max_sessions: int = 10,
):
    """
    Detect and list Zoom recordings in default save locations.
    
    Note: This endpoint can only access files on the server's filesystem.
    For client-side file access, use the frontend file picker.
    """
    from api.services.zoom.recording_detector import detect_zoom_recordings
    
    try:
        recordings = detect_zoom_recordings(max_sessions=max_sessions)
        
        result = []
        for rec in recordings:
            result.append({
                "session_name": rec.session_name,
                "session_path": str(rec.session_path),
                "audio_tracks": [
                    {
                        "path": str(audio_path),
                        "participant_name": participant_name,
                        "size_bytes": audio_path.stat().st_size if audio_path.exists() else 0,
                    }
                    for audio_path, participant_name in rec.audio_files
                ],
                "video_file": str(rec.video_file) if rec.video_file else None,
                "timestamp": rec.timestamp,
            })
        
        return result
    
    except Exception as e:
        import logging
        log = logging.getLogger("api.media.zoom")
        log.error(f"[zoom] Failed to detect recordings: {e}", exc_info=True)
        # Return empty list rather than failing - user can still upload manually
        return []

@router.get("/{media_id}", response_model=MediaItem)
async def get_media_item(
    media_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Retrieve a specific media item by ID."""
    item = session.get(MediaItem, media_id)
    if not item:
        raise HTTPException(status_code=404, detail="Media item not found")
    if str(item.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not authorized to access this media item")
    return item