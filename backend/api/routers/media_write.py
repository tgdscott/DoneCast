import json
from uuid import uuid4, UUID
from typing import List, Optional
from pathlib import Path

from fastapi import APIRouter, HTTPException, status, Depends, UploadFile, File, Form
import logging
from sqlmodel import Session, select

from api.core.paths import MEDIA_DIR
from api.models.podcast import MediaItem, MediaCategory
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
):
	"""Upload one or more media files with optional friendly names."""
	created_items = []
	names = json.loads(friendly_names) if friendly_names else []

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
		if type_prefix and not ct.startswith(type_prefix):
			expected = "audio" if type_prefix == AUDIO_PREFIX else "image"
			raise HTTPException(status_code=400, detail=f"Invalid file type '{ct or 'unknown'}'. Expected {expected} file for category '{cat.value}'.")
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

		friendly_name = names[i] if i < len(names) and names[i].strip() else default_friendly_name

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

		try:
			if category == MediaCategory.main_content:
				from worker.tasks import transcribe_media_file  # type: ignore
				transcribe_media_file.delay(safe_filename)
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
