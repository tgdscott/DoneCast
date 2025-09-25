import shutil
import json
from uuid import uuid4
import subprocess
import os
from fastapi import APIRouter, HTTPException, status, Depends, UploadFile, File, Form
from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID
from pathlib import Path
from sqlmodel import Session, select
from sqlalchemy import text as _sa_text
from sqlalchemy import desc as _sa_desc

from ..models.podcast import MediaItem, MediaCategory
from ..models.user import User
from ..core.database import get_session
from api.core.auth import get_current_user

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
        MediaCategory.main_content: 500 * MB,
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

        media_item = MediaItem(
            filename=safe_filename,
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
                # Import lazily to avoid circular import at startup
                from worker.tasks import transcribe_media_file  # type: ignore
                transcribe_media_file.delay(safe_filename)
        except Exception:
            # Non-fatal; upload should still succeed
            pass

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

    file_path = MEDIA_DIR / media_item.filename
    if file_path.exists():
        file_path.unlink()
        
    session.delete(media_item)
    session.commit()
    
    return None