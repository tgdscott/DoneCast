from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple
from urllib.parse import quote_plus
from uuid import UUID, uuid4

from fastapi import HTTPException, UploadFile, status

from ...models.podcast import DistributionStatus

MB = 1024 * 1024


def sanitize_cover_filename(filename: str) -> str:
    """Return a filesystem-safe representation of ``filename``."""
    name = Path(filename or "cover").name
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", name).strip("._")
    return safe or "cover"


def save_cover_upload(
    cover_image: UploadFile,
    user_id: UUID,
    *,
    upload_dir: Path,
    max_bytes: int = 10 * MB,
    allowed_extensions: Optional[Iterable[str]] = None,
    require_image_content_type: bool = False,
) -> Tuple[str, Path]:
    """Persist an uploaded cover image to cloud storage (R2 or GCS) with temporary local staging.

    Returns the storage URL (gs://... or https://...) as filename and temp path. 
    Raises :class:`HTTPException` for validation issues so API handlers can surface friendly errors.
    """
    import os

    if not cover_image or not cover_image.filename:
        raise HTTPException(status_code=400, detail="Cover image filename missing.")

    extension = Path(cover_image.filename).suffix.lower()
    if allowed_extensions is not None:
        allowed = {ext.lower() for ext in allowed_extensions}
        if extension not in allowed:
            raise HTTPException(
                status_code=400,
                detail="Unsupported cover image extension. Allowed: "
                + ", ".join(sorted(allowed)),
            )

    # Always capture content_type for cloud storage upload
    content_type = (getattr(cover_image, "content_type", "") or "").lower()
    
    if require_image_content_type:
        if not content_type.startswith("image/"):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid cover content type '{content_type or 'unknown'}'. Expected image/*.",
            )

    upload_dir.mkdir(parents=True, exist_ok=True)

    safe_name = sanitize_cover_filename(cover_image.filename)
    file_extension = Path(safe_name).suffix.lower() or extension or ".png"
    unique_filename = f"{user_id.hex}/covers/{user_id}_{uuid4()}{file_extension}"
    temp_path = upload_dir / f"{user_id}_{uuid4()}{file_extension}"

    # Stage to /tmp temporarily
    total = 0
    try:
        with temp_path.open("wb") as buffer:
            while True:
                chunk = cover_image.file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if max_bytes and total > max_bytes:
                    try:
                        temp_path.unlink(missing_ok=True)  # type: ignore[call-arg]
                    except Exception:
                        pass
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="Cover image exceeds 10 MB limit.",
                    )
                buffer.write(chunk)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive cleanup
        try:
            temp_path.unlink(missing_ok=True)  # type: ignore[call-arg]
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Failed to store cover image: {exc}") from exc

    # Process image constraints (resize/compress) before uploading
    # This ensures the uploaded image meets platform requirements
    try:
        from ...services.image_utils import ensure_cover_image_constraints
        processed_path = ensure_cover_image_constraints(str(temp_path))
        # If processing created a new file, use that instead
        if processed_path != str(temp_path) and Path(processed_path).exists():
            # Clean up original temp file
            try:
                temp_path.unlink(missing_ok=True)  # type: ignore[call-arg]
            except Exception:
                pass
            temp_path = Path(processed_path)
    except Exception as img_err:
        # Non-fatal: if image processing fails, continue with original
        import logging
        logging.getLogger(__name__).warning(f"Image processing failed, using original: {img_err}")

    # Upload to cloud storage (R2 or GCS based on STORAGE_BACKEND)
    try:
        from infrastructure import storage
        with open(temp_path, "rb") as f:
            # Use storage routing module - routes to R2 if STORAGE_BACKEND=r2, otherwise GCS
            # Disable fallback - podcast covers MUST be in cloud storage
            storage_url = storage.upload_fileobj(
                bucket_name="",  # Ignored, uses configured bucket from env vars
                key=unique_filename,
                fileobj=f,
                content_type=content_type or "image/jpeg",
                allow_fallback=False
            )
        
        # Clean up temp file
        try:
            temp_path.unlink(missing_ok=True)  # type: ignore[call-arg]
        except Exception:
            pass
        
        # Verify upload succeeded
        if not storage_url:
            raise Exception("Cloud storage upload returned None")
        
        # Accept both gs:// (GCS) and https:// (R2) URLs
        if not (storage_url.startswith("gs://") or storage_url.startswith("https://") or storage_url.startswith("http://")):
            raise Exception(f"Cloud storage upload returned invalid URL format: {storage_url}")
        
        # Return storage URL as filename
        return storage_url, temp_path  # temp_path for backward compat (may not exist anymore)
        
    except Exception as e:
        # Clean up temp file and fail
        try:
            temp_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to upload cover to cloud storage: {str(e)}"
        ) from e


def build_distribution_context(podcast: "Podcast", session: Optional["Session"] = None) -> Dict[str, Optional[str]]:
    from ...models.podcast import Podcast, Episode, EpisodeStatus  # Local import to avoid circular refs
    from sqlmodel import select

    if not isinstance(podcast, Podcast):
        raise TypeError("podcast must be a Podcast instance")

    rss_url = (
        getattr(podcast, "rss_feed_url", None)
        or getattr(podcast, "rss_url_locked", None)
        or getattr(podcast, "rss_url", None)
    )
    # If rss_url is still None, use the property directly (it always returns a value)
    if not rss_url:
        rss_url = podcast.rss_feed_url
    
    spreaker_show_id = getattr(podcast, "spreaker_show_id", None)
    spreaker_show_url = f"https://www.spreaker.com/show/{spreaker_show_id}" if spreaker_show_id else None
    encoded_rss = quote_plus(rss_url) if rss_url else ""
    
    # Check if podcast has published episodes (required for Apple/Spotify submission)
    has_published_episodes = False
    if session:
        try:
            published_count = session.exec(
                select(Episode)
                .where(Episode.podcast_id == podcast.id)
                .where(Episode.status == EpisodeStatus.published)
                .where(Episode.gcs_audio_path != None)  # Must have audio
            ).all()
            has_published_episodes = len(published_count) > 0
        except Exception:
            # If query fails, assume no episodes (safer default)
            has_published_episodes = False
    
    return {
        "rss_feed_url": rss_url,
        "rss_feed_encoded": encoded_rss,
        "rss_feed_or_placeholder": rss_url or "your Plus Plus RSS feed",
        "spreaker_show_id": spreaker_show_id or "",
        "spreaker_show_url": spreaker_show_url,
        "podcast_name": getattr(podcast, "name", None) or "",
        "has_published_episodes": str(has_published_episodes).lower(),  # Convert to string for template compatibility
    }


def format_distribution_template(value: Optional[str], context: Dict[str, Optional[str]]) -> Optional[str]:
    if not value:
        return value
    safe = defaultdict(str)
    for key, val in context.items():
        safe[key] = "" if val is None else str(val)
    try:
        return value.format_map(safe)
    except Exception:
        return value


def build_distribution_item_payload(
    host_def: Dict[str, object],
    status: Optional["PodcastDistributionStatus"],
    context: Dict[str, Optional[str]],
) -> Dict[str, object]:
    from ...models.podcast import PodcastDistributionStatus  # Local import to avoid circular refs

    disabled_reason: Optional[str] = None
    requires_rss_feed = bool(host_def.get("requires_rss_feed"))
    requires_spreaker_show = bool(host_def.get("requires_spreaker_show"))
    
    # Check RSS feed availability and published episodes
    has_rss_feed = bool(context.get("rss_feed_url"))
    has_published_episodes = context.get("has_published_episodes", "false").lower() == "true"
    
    if requires_rss_feed:
        if not has_rss_feed:
            disabled_reason = host_def.get("rss_missing_help") or "Add your RSS feed first."
        elif not has_published_episodes:
            # RSS feed exists but no episodes - platforms will reject it
            disabled_reason = (
                "Publish at least one episode before submitting. "
                "Apple Podcasts and Spotify require episodes with audio in your RSS feed."
            )
    
    if requires_spreaker_show and not context.get("spreaker_show_id"):
        disabled_reason = host_def.get("spreaker_missing_help") or "Link your show to Spreaker first."

    default_status_key = host_def.get("default_status") or DistributionStatus.not_started.value
    try:
        default_status = DistributionStatus(default_status_key)
    except Exception:
        default_status = DistributionStatus.not_started

    current_status = default_status
    notes = None
    updated_at = None
    if status is not None:
        try:
            current_status = DistributionStatus(status.status)
        except Exception:
            current_status = default_status
        notes = status.notes
        updated_at = getattr(status, "updated_at", None)

    instructions_list: list[str] = []
    for text in (host_def.get("instructions") or []):
        if not text:
            continue
        formatted = format_distribution_template(str(text), context)
        if formatted:
            instructions_list.append(formatted)

    action_url = format_distribution_template(host_def.get("action_url_template"), context)
    if not action_url:
        action_url = format_distribution_template(host_def.get("action_url"), context)
    docs_url = format_distribution_template(host_def.get("docs_url"), context)

    return {
        "key": str(host_def.get("key")),
        "name": str(host_def.get("name") or host_def.get("key")),
        "summary": format_distribution_template(host_def.get("summary"), context),
        "automation": str(host_def.get("automation", "manual")),
        "automation_notes": format_distribution_template(host_def.get("automation_notes"), context),
        "action_label": host_def.get("action_label"),
        "action_url": action_url,
        "docs_url": docs_url,
        "instructions": instructions_list,
        "requires_rss_feed": requires_rss_feed,
        "requires_spreaker_show": requires_spreaker_show,
        "disabled_reason": disabled_reason,
        "status": current_status,
        "notes": notes,
        "status_updated_at": updated_at,
    }


__all__ = [
    "save_cover_upload",
    "sanitize_cover_filename",
    "build_distribution_context",
    "format_distribution_template",
    "build_distribution_item_payload",
]
