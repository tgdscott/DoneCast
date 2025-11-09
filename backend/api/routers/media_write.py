import json
import os
from uuid import uuid4, UUID
from typing import List, Optional
from pathlib import Path

from fastapi import APIRouter, HTTPException, status, Depends, UploadFile, File, Form
import logging
from sqlmodel import Session, select

from api.core.paths import MEDIA_DIR
from api.models.podcast import MediaItem, MediaCategory
from api.models.transcription import TranscriptionWatch
from api.models.user import User
from api.core.database import get_session
from api.routers.auth import get_current_user

from .media_schemas import MediaItemUpdate
from .media_common import sanitize_name, copy_with_limit

router = APIRouter(prefix="/media", tags=["Media Library"])
log = logging.getLogger("media.upload")

# Ensure upload logs are visible
logging.getLogger("media.upload").setLevel(logging.INFO)
logging.getLogger("infrastructure.storage").setLevel(logging.INFO)
logging.getLogger("infrastructure.gcs").setLevel(logging.INFO)


@router.post("/upload/{category}", response_model=List[MediaItem], status_code=status.HTTP_201_CREATED)
async def upload_media_files(
	category: MediaCategory,
	session: Session = Depends(get_session),
	current_user: User = Depends(get_current_user),
        files: List[UploadFile] = File(...),
        friendly_names: Optional[str] = Form(None),
        notify_when_ready: Optional[str] = Form(None),
        notify_email: Optional[str] = Form(None),
):
        """Upload one or more media files with optional friendly names."""
        created_items = []
        names = json.loads(friendly_names) if friendly_names else []

        require_friendly = category == MediaCategory.main_content

        notify_requested = False
        if isinstance(notify_when_ready, str):
            notify_requested = notify_when_ready.strip().lower() in {"1", "true", "yes", "on"}
        elif notify_when_ready:
            notify_requested = True

        notify_target = (notify_email or "").strip()
        if notify_requested and not notify_target:
            notify_target = (current_user.email or "").strip() if hasattr(current_user, "email") else ""
        if notify_target and "@" not in notify_target:
            notify_target = ""

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
		
		# Get file extension first for validation
		ext = Path(f.filename or "").suffix.lower()
		if not ext:
			raise HTTPException(status_code=400, detail="File must have an extension.")
		
		# Determine allowed extensions based on category
		allowed = AUDIO_EXTS if type_prefix == AUDIO_PREFIX else IMAGE_EXTS
		if ext not in allowed:
			raise HTTPException(status_code=400, detail=f"Unsupported file extension '{ext}'.")
		
		# If content type is provided, validate it matches the category
		# But allow missing content type if extension is valid (for browser recordings)
		if ct and type_prefix and not ct.startswith(type_prefix):
			expected = "audio" if type_prefix == AUDIO_PREFIX else "image"
			raise HTTPException(status_code=400, detail=f"Invalid file type '{ct}'. Expected {expected} file for category '{cat.value}'.")

	for i, file in enumerate(files):
		if not file.filename:
			continue
		
		# Log upload request received - this helps diagnose if upload endpoint is being called
		log.info("[upload.request] Received upload request: category=%s, filename=%s, user_id=%s", 
		        category.value, file.filename, current_user.id)

		_validate_meta(file, category)

		original_filename = Path(file.filename).stem
		default_friendly_name = ' '.join(original_filename.split('_')).title()

		safe_orig = sanitize_name(file.filename)
		safe_filename = f"{current_user.id.hex}_{uuid4().hex}_{safe_orig}"

		max_bytes = CATEGORY_SIZE_LIMITS.get(category, 50 * MB)
		
		# Check file size early to provide helpful error messages
		# Cloud Run has a 32MB request body limit, so files >25MB may fail with multipart encoding overhead
		CLOUD_RUN_LIMIT = 32 * MB
		WARNING_THRESHOLD = 25 * MB  # Warn users about files that may hit the limit
		
		# Try to get file size without reading the entire file
		file_size = None
		try:
			# Some upload implementations expose file size
			if hasattr(file, 'size') and file.size:
				file_size = file.size
			elif hasattr(file.file, 'seek') and hasattr(file.file, 'tell'):
				# Try to get size by seeking to end
				current_pos = file.file.tell()
				file.file.seek(0, 2)  # Seek to end
				file_size = file.file.tell()
				file.file.seek(current_pos, 0)  # Seek back
		except Exception:
			pass  # Size unknown, will check after reading
		
		# Warn if file is large enough to potentially hit Cloud Run's limit
		if file_size and file_size > WARNING_THRESHOLD:
			log.warning("[upload.request] Large file detected: %s bytes (%.1f MB). May hit Cloud Run's 32MB limit with multipart encoding.", 
			           file_size, file_size / MB)
			# Note: We can't prevent the upload here, but we'll provide a better error message if it fails
		
		# **CRITICAL**: ALL files MUST be uploaded to GCS - no local storage fallback
		# This ensures files are accessible to worker servers and production environments
		gcs_bucket = os.getenv("GCS_BUCKET", "ppp-media-us-west1")
		if not gcs_bucket:
			raise HTTPException(status_code=500, detail="GCS_BUCKET environment variable not set - cloud storage is required")
		
		# Read file content and get size
		# Note: For files >25MB, this may fail due to Cloud Run's 32MB request body limit
		try:
			file_content = file.file.read(max_bytes)
			bytes_written = len(file_content)
		except Exception as read_err:
			# If reading fails, it might be due to Cloud Run's request size limit
			error_msg = str(read_err).lower()
			if "413" in error_msg or "too large" in error_msg or "request entity too large" in error_msg:
				log.error("[upload.request] File upload failed due to size limit: %s", file.filename)
				raise HTTPException(
					status_code=413,
					detail=f"File is too large for standard upload (Cloud Run limit: 32MB). Files larger than 25MB should use direct upload. Please try uploading again - the system will automatically use direct upload for large files."
				)
			else:
				# Re-raise other errors
				raise
		
		log.info("[upload.storage] Starting upload for %s: filename=%s, size=%d bytes, bucket=%s", 
		        category.value, safe_filename, bytes_written, gcs_bucket)
		
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
			
			if bytes_written >= max_bytes:
				# Check if there's more data
				remaining = file.file.read(1)
				if remaining:
					raise HTTPException(status_code=413, detail=f"File exceeds maximum size of {max_bytes / MB:.1f} MB")
			
			# Upload directly to GCS from memory - NO local file write, NO R2
			# CRITICAL: allow_fallback=False to ensure files are ALWAYS uploaded to GCS
			from io import BytesIO
			file_stream = BytesIO(file_content)
			storage_url = gcs.upload_fileobj(
				gcs_bucket,
				storage_key,
				file_stream,
				content_type=file.content_type or ("audio/mpeg" if category != MediaCategory.podcast_cover and category != MediaCategory.episode_cover else "image/jpeg"),
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
				safe_filename = storage_url
				log.info("[upload.storage] SUCCESS: %s uploaded to GCS: %s", category.value, storage_url)
				log.info("[upload.storage] MediaItem will be saved with filename='%s'", safe_filename)
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

                provided_name = names[i] if i < len(names) else None
                provided_clean = str(provided_name).strip() if provided_name is not None else ""
                if require_friendly and not provided_clean:
                        raise HTTPException(
                                status_code=400,
                                detail="Friendly name is required when uploading episode audio.",
                        )

                friendly_name = provided_name if provided_clean else default_friendly_name

                # Verify safe_filename is a GCS URL before saving (intermediate files always go to GCS)
                if not safe_filename.startswith("gs://"):
                    log.error("[upload.storage] CRITICAL: safe_filename is not a GCS URL: '%s'", safe_filename)
                    log.error("[upload.storage] Expected gs:// URL for intermediate file upload")
                    raise HTTPException(
                        status_code=500,
                        detail=f"Internal error: filename is not a GCS URL. This indicates a bug in the upload process."
                    )
                
                log.info("[upload.storage] Creating MediaItem with filename='%s' (GCS URL)", safe_filename)
                media_item = MediaItem(
                        filename=safe_filename,
                        friendly_name=friendly_name,
                        content_type=(file.content_type or None),
                        filesize=bytes_written,
                        user_id=current_user.id,
                        category=category,
                )
                session.add(media_item)
                created_items.append(media_item)
                log.info("[upload.storage] MediaItem created: id=%s, filename='%s'", media_item.id, media_item.filename)

                if (
                    category == MediaCategory.main_content
                    and notify_requested
                    and notify_target
                ):
                    try:
                        existing_watch = session.exec(
                            select(TranscriptionWatch).where(
                                TranscriptionWatch.user_id == current_user.id,
                                TranscriptionWatch.filename == safe_filename,
                            )
                        ).first()
                    except Exception:
                        existing_watch = None

                    if existing_watch:
                        existing_watch.notify_email = notify_target
                        existing_watch.friendly_name = friendly_name
                        existing_watch.notified_at = None
                        existing_watch.last_status = "queued"
                        session.add(existing_watch)
                    else:
                        session.add(
                            TranscriptionWatch(
                                user_id=current_user.id,
                                filename=safe_filename,
                                friendly_name=friendly_name,
                                notify_email=notify_target,
                                last_status="queued",
                            )
                        )

                try:
                        if category == MediaCategory.main_content:
				from worker.tasks import transcribe_media_file  # type: ignore
				transcribe_media_file.delay(safe_filename, str(current_user.id))
		except Exception:
			pass

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

	return created_items


@router.get("/", response_model=List[MediaItem])
async def list_user_media(
	session: Session = Depends(get_session),
	current_user: User = Depends(get_current_user)
):
	"""Retrieve the current user's media library, filtering out main content and covers.

	Only return items in categories: intro, outro, music, sfx, commercial.
	"""
	from sqlalchemy import text as _sa_text
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
	current_user: User = Depends(get_current_user),
):
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
async def delete_media_item(
	media_id: UUID,
	session: Session = Depends(get_session),
	current_user: User = Depends(get_current_user),
):
	statement = select(MediaItem).where(MediaItem.id == media_id, MediaItem.user_id == current_user.id)
	media_item = session.exec(statement).one_or_none()

	if not media_item:
		raise HTTPException(status_code=404, detail="Media item not found or you don't have permission to delete it.")

	# Delete from cloud storage if it's a GCS/R2 URL
	filename = media_item.filename
	if filename and (filename.startswith("gs://") or filename.startswith("http")):
		try:
			from infrastructure import storage
			# Extract bucket and key from URL
			if filename.startswith("gs://"):
				# gs://bucket/key
				parts = filename[5:].split("/", 1)
				if len(parts) == 2:
					bucket, key = parts
					storage.delete_blob(bucket, key)
					log.info("[delete] Deleted %s from GCS", filename)
			elif "r2.cloudflarestorage.com" in filename:
				# https://bucket.r2.cloudflarestorage.com/key
				# Extract bucket and key from URL
				import re
				match = re.search(r'https://([^.]+)\.r2\.cloudflarestorage\.com/(.+)', filename)
				if match:
					bucket, key = match.groups()
					storage.delete_blob(bucket, key)
					log.info("[delete] Deleted %s from R2", filename)
		except Exception as e:
			log.warning("[delete] Failed to delete %s from cloud storage: %s", filename, e)
			# Continue with DB deletion even if cloud storage deletion fails

	session.delete(media_item)
	session.commit()

	return None
