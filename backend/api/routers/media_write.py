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

		_validate_meta(file, category)

		original_filename = Path(file.filename).stem
		default_friendly_name = ' '.join(original_filename.split('_')).title()

		safe_orig = sanitize_name(file.filename)
		safe_filename = f"{current_user.id.hex}_{uuid4().hex}_{safe_orig}"
		file_path = MEDIA_DIR / safe_filename

		max_bytes = CATEGORY_SIZE_LIMITS.get(category, 50 * MB)
		try:
			bytes_written = copy_with_limit(file.file, file_path, max_bytes)
		except HTTPException:
			try:
				if file_path.exists():
					file_path.unlink()
			finally:
				pass
			raise
		except Exception as e:
			log.error("[upload.write] failed writing %s: %s", safe_filename, e)
			try:
				if file_path.exists():
					file_path.unlink()
			finally:
				pass
			raise HTTPException(status_code=500, detail="Failed to save uploaded file.")

		# Upload to GCS for persistence (intro/outro/music/sfx/commercial)
		# **CRITICAL**: These categories MUST be in GCS for production
		gcs_bucket = os.getenv("GCS_BUCKET", "ppp-media-us-west1")
		if gcs_bucket and category in (
			MediaCategory.intro,
			MediaCategory.outro,
			MediaCategory.music,
			MediaCategory.sfx,
			MediaCategory.commercial,
		):
			try:
				from infrastructure import storage
				storage_key = f"{current_user.id.hex}/media/{category.value}/{safe_filename}"
				log.info("[upload.storage] Uploading %s to bucket (backend: %s), key: %s", category.value, os.getenv("STORAGE_BACKEND", "gcs"), storage_key)
				with open(file_path, "rb") as f:
					# Upload to configured storage backend (R2 or GCS)
					storage_url = storage.upload_fileobj(
						gcs_bucket,  # Bucket name (abstraction layer uses correct backend)
						storage_key, 
						f, 
						content_type=file.content_type or "audio/mpeg"
					)
				
				# Store storage URL instead of local filename for persistence
				# URL format depends on backend: gs://bucket/key (GCS) or https://bucket.r2.cloudflarestorage.com/key (R2)
				if storage_url and (storage_url.startswith("gs://") or storage_url.startswith("http")):
					safe_filename = storage_url
					log.info("[upload.storage] SUCCESS: %s uploaded: %s", category.value, storage_url)
				else:
					# This should never happen, but belt-and-suspenders
					log.error("[upload.storage] Upload returned invalid URL: %s", storage_url)
					# Clean up local file
					try:
						if file_path.exists():
							file_path.unlink()
					except Exception:
						pass
					raise HTTPException(
						status_code=500,
						detail=f"Failed to upload {category.value} to cloud storage - this is required for production use"
					)
			except HTTPException:
				raise
			except Exception as e:
				log.error("[upload.storage] CRITICAL: Failed to upload %s to storage backend: %s", category.value, e, exc_info=True)
				# Clean up local file
				try:
					if file_path.exists():
						file_path.unlink()
				except Exception:
					pass
				raise HTTPException(
					status_code=500,
					detail=f"Failed to upload {category.value} to cloud storage: {str(e)}"
				)

                provided_name = names[i] if i < len(names) else None
                provided_clean = str(provided_name).strip() if provided_name is not None else ""
                if require_friendly and not provided_clean:
                        raise HTTPException(
                                status_code=400,
                                detail="Friendly name is required when uploading episode audio.",
                        )

                friendly_name = provided_name if provided_clean else default_friendly_name

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

	# Commit and cleanup on failure
	try:
		session.commit()
	except Exception as e:
		log.error("[upload.db] commit failed for %d items in category=%s: %s", len(created_items), category.value, e)
		# remove any files written for this batch
		for item in created_items:
			try:
				p = MEDIA_DIR / item.filename
				if p.exists():
					p.unlink()
			except Exception:
				pass
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

	file_path = MEDIA_DIR / media_item.filename
	if file_path.exists():
		file_path.unlink()

	session.delete(media_item)
	session.commit()

	return None
