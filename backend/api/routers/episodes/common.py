import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from api.core.paths import FINAL_DIR, MEDIA_DIR


def _final_url_for(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    base = os.path.basename(str(path))
    try:
        if (FINAL_DIR / base).is_file():
            return f"/static/final/{base}"
    except Exception:
        pass
    try:
        if (MEDIA_DIR / base).is_file():
            return f"/static/media/{base}"
    except Exception:
        pass
    # Don't return URL if file doesn't exist - return None instead
    # This prevents 404 errors on episode history page
    return None


def _cover_url_for(path: Optional[str], *, gcs_path: Optional[str] = None) -> Optional[str]:
    """Generate cover URL with priority: GCS/R2 > remote > local.
    
    Args:
        path: Local path or remote URL (legacy)
        gcs_path: GCS path (gs://...) or R2 URL (https://...) if available
    """
    # Priority 1: GCS URL (gs://) - generate signed URL
    if gcs_path and str(gcs_path).startswith("gs://"):
        try:
            from infrastructure.gcs import get_signed_url
            gcs_str = str(gcs_path)[5:]  # Remove "gs://"
            parts = gcs_str.split("/", 1)
            if len(parts) == 2:
                bucket, key = parts
                url = get_signed_url(bucket, key, expiration=3600)
                if url:
                    return url
        except Exception as e:
            from api.core.logging import get_logger
            logger = get_logger("api.episodes.common")
            logger.warning("GCS URL generation failed for %s: %s", gcs_path, e)
            # Fall through to path-based resolution
    
    # Priority 1b: R2 URL (https://) - use directly (R2 URLs are already public/signed)
    if gcs_path and str(gcs_path).lower().startswith(("http://", "https://")):
        # R2 URLs stored in gcs_cover_path are already public URLs, use them directly
        return str(gcs_path)
    
    # Priority 2: Remote URL (Spreaker hosted)
    if not path:
        return None
    p = str(path)
    if p.lower().startswith(("http://", "https://")):
        return p
    
    # Priority 3: Local file (only if exists)
    try:
        basename = os.path.basename(p)
        local_path = MEDIA_DIR / basename
        if local_path.exists() and local_path.is_file():
            return f"/static/media/{basename}"
    except Exception:
        pass
    
    # No valid source found - return None instead of invalid URL
    return None


def _status_value(s):
    try:
        return str(getattr(s, 'value', s) or '').lower()
    except Exception:
        return str(s or '').lower()


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if not dt:
        return None
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_iso_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        text = str(value).strip()
        if not text:
            return None
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _local_final_candidates(path: Optional[str]) -> list[Path]:
    candidates: list[Path] = []
    if not path:
        return candidates
    try:
        raw = Path(str(path))
        candidates.append(raw if raw.is_absolute() else raw)
        try:
            resolved = raw.resolve()
            if resolved not in candidates:
                candidates.append(resolved)
        except Exception:
            pass
    except Exception:
        raw = None
    base = os.path.basename(str(path))
    if base:
        for base_dir in (FINAL_DIR, MEDIA_DIR):
            try:
                cand = (base_dir / base).resolve()
            except Exception:
                cand = base_dir / base
            if cand not in candidates:
                candidates.append(cand)
    return candidates


def compute_playback_info(episode: Any, *, now: Optional[datetime] = None) -> dict[str, Any]:
    """Determine playback URL from R2/GCS or Spreaker.

    Priority order for audio URLs:
    1. R2/GCS URL (gcs_audio_path) - Primary storage for YOUR episodes
    2. Spreaker stream URL - For Spreaker-hosted episodes

    NO LOCAL FILES - cloud storage or Spreaker only.
    
    Returns keys compatible with existing episode serializers.
    """

    now_utc = _as_utc(now) or datetime.now(timezone.utc)
    
    # Priority 1: Cloud storage (R2 or GCS)
    gcs_audio_path = getattr(episode, "gcs_audio_path", None)
    final_audio_url = None
    cloud_exists = False
    
    if gcs_audio_path:
        storage_url = str(gcs_audio_path)
        try:
            # R2 paths: r2://bucket/key or https://bucket.account.r2.cloudflarestorage.com/key
            if storage_url.startswith("https://") and ".r2.cloudflarestorage.com/" in storage_url:
                # R2 storage URL - needs signed URL for playback
                # Parse: https://ppp-media.{account}.r2.cloudflarestorage.com/user/episodes/123/audio/file.mp3
                from infrastructure.r2 import get_signed_url
                import os
                
                # Extract bucket and key from URL
                account_id = os.getenv("R2_ACCOUNT_ID", "").strip()
                if account_id and f".{account_id}.r2.cloudflarestorage.com/" in storage_url:
                    # Find bucket name (between https:// and first dot)
                    url_parts = storage_url.replace("https://", "").split("/", 1)
                    if len(url_parts) == 2:
                        bucket_part = url_parts[0]  # e.g., "ppp-media.{account}.r2.cloudflarestorage.com"
                        key = url_parts[1]  # e.g., "user/episodes/123/audio/file.mp3"
                        bucket = bucket_part.split(".")[0]  # Extract "ppp-media"
                        
                        final_audio_url = get_signed_url(bucket, key, expiration=86400)  # 24hr expiry
                        cloud_exists = True
                else:
                    # Account ID mismatch or missing - log warning but don't fail
                    from api.core.logging import get_logger
                    logger = get_logger("api.episodes.common")
                    logger.warning("R2 URL detected but cannot parse: %s (account_id=%s)", storage_url, account_id)
            elif storage_url.startswith("https://"):
                # Other HTTPS URL (legacy Spreaker or other) - use directly
                final_audio_url = storage_url
                cloud_exists = True
            elif storage_url.startswith("r2://"):
                # R2 URI format - needs signed URL
                from infrastructure.r2 import get_signed_url
                r2_str = storage_url[5:]  # Remove "r2://"
                parts = r2_str.split("/", 1)
                if len(parts) == 2:
                    bucket, key = parts
                    final_audio_url = get_signed_url(bucket, key, expiration=86400)  # 24hr expiry
                    cloud_exists = True
            elif storage_url.startswith("gs://"):
                # Legacy GCS - will migrate to R2
                from infrastructure.gcs import get_signed_url
                gcs_str = storage_url[5:]  # Remove "gs://"
                parts = gcs_str.split("/", 1)
                if len(parts) == 2:
                    bucket, key = parts
                    final_audio_url = get_signed_url(bucket, key, expiration=3600)
                    cloud_exists = True
        except Exception as err:
            from api.core.logging import get_logger
            logger = get_logger("api.episodes.common")
            logger.error("Cloud storage URL generation failed for %s: %s", gcs_audio_path, err)

    # Priority 2: Spreaker stream URL (for Spreaker-hosted episodes)
    stream_url = None
    try:
        spk_id = getattr(episode, "spreaker_episode_id", None)
        if spk_id:
            stream_url = f"https://api.spreaker.com/v2/episodes/{spk_id}/play"
    except Exception:
        stream_url = None

    # Determine final playback URL
    playback_url = final_audio_url if final_audio_url else stream_url
    playback_type = "cloud" if final_audio_url else ("spreaker" if stream_url else "none")
    audio_available = bool(cloud_exists or stream_url)

    return {
        "final_audio_url": final_audio_url,  # Cloud storage URL or None
        "stream_url": stream_url,  # Spreaker stream or None
        "playback_url": playback_url,  # The actual URL to use
        "playback_type": playback_type,  # "cloud", "spreaker", or "none"
        "final_audio_exists": audio_available,  # True if any audio source exists
        "gcs_exists": cloud_exists,  # True if cloud file exists (legacy key name)
        "prefer_remote_audio": False,  # Deprecated
    }


def compute_cover_info(episode: Any, *, now: Optional[datetime] = None) -> dict[str, Any]:
    """Determine cover preference between GCS, local, and Spreaker cover.

    Priority order for cover URLs within 7-day window:
    1. GCS URL (gcs_cover_path) - original cover during retention
    2. Local file (cover_path)
    3. Spreaker cover URL (remote_cover_url)

    After 7 days: Uses Spreaker cover (remote_cover_url) if available.
    Always falls back to remote_cover_url if all else fails.

    Returns dict with 'cover_url' key compatible with existing serializers.
    """
    now_utc = _as_utc(now) or datetime.now(timezone.utc)
    
    # Get cover fields from episode
    gcs_cover_path = getattr(episode, "gcs_cover_path", None)
    cover_path = getattr(episode, "cover_path", None)
    remote_cover_url = getattr(episode, "remote_cover_url", None)
    
    status_str = _status_value(getattr(episode, "status", None))
    publish_at = _as_utc(getattr(episode, "publish_at", None))
    episode_id = getattr(episode, "id", None)
    
    # Debug logging for cover resolution (INFO level for troubleshooting)
    from api.core.logging import get_logger
    logger = get_logger("api.episodes.common")
    logger.info(
        "[compute_cover_info] episode_id=%s status=%s gcs_cover_path=%s cover_path=%s remote_cover_url=%s",
        episode_id, status_str, 
        gcs_cover_path[:100] + "..." if gcs_cover_path and len(str(gcs_cover_path)) > 100 else gcs_cover_path,
        cover_path, 
        remote_cover_url
    )
    
    # Determine if within 7-day window
    within_7days = False
    if publish_at and status_str in ("published", "scheduled"):
        # Only apply grace period after actual publish time
        if now_utc >= publish_at:
            days_since_publish = (now_utc - publish_at).days
            within_7days = days_since_publish < 7
    
    # Build cover URL based on priority
    cover_url = None
    cover_source = "none"
    
    # Try gcs_cover_path (GCS or R2)
    # R2 URLs (https://) are ALWAYS valid and should ALWAYS be used
    # GCS URLs (gs://) are only valid within 7-day window for published episodes (retention policy)
    # For unpublished episodes, always use gcs_cover_path if available
    if gcs_cover_path:
        gcs_cover_str = str(gcs_cover_path).strip()
        if gcs_cover_str:  # Only process non-empty strings
            is_r2_url = gcs_cover_str.lower().startswith(("http://", "https://"))
            is_published = status_str in ("published", "scheduled")
            
            # CRITICAL: Always use R2 URLs immediately (they're permanent, no conditions)
            # For GCS URLs: use if unpublished, or if published and within 7-day window
            should_use = is_r2_url or (not is_published) or (is_published and within_7days)
            
            logger.info(
                "[compute_cover_info] episode_id=%s evaluating gcs_cover_path: is_r2_url=%s is_published=%s within_7days=%s should_use=%s",
                episode_id, is_r2_url, is_published, within_7days, should_use
            )
            
            if should_use:
                cover_url = _cover_url_for(None, gcs_path=gcs_cover_path)
                if cover_url:
                    cover_source = "r2" if is_r2_url else "gcs"
                    logger.info(
                        "[compute_cover_info] episode_id=%s ✅ resolved cover_url from gcs_cover_path: %s (source=%s)",
                        episode_id, cover_url[:100] + "..." if len(cover_url) > 100 else cover_url, cover_source
                    )
                else:
                    logger.error(
                        "[compute_cover_info] episode_id=%s ❌ CRITICAL: _cover_url_for returned None for gcs_cover_path=%s. "
                        "This should never happen for R2 URLs. Check _cover_url_for implementation.",
                        episode_id, gcs_cover_path[:100] + "..." if gcs_cover_path and len(str(gcs_cover_path)) > 100 else gcs_cover_path
                    )
            else:
                logger.warning(
                    "[compute_cover_info] episode_id=%s ⚠️ skipping gcs_cover_path (GCS URL outside retention window): is_r2_url=%s is_published=%s within_7days=%s",
                    episode_id, is_r2_url, is_published, within_7days
                )
    
    # Try local/remote cover_path
    if not cover_url and cover_path:
        logger.info("[compute_cover_info] episode_id=%s trying cover_path: %s", episode_id, cover_path)
        cover_url = _cover_url_for(cover_path)
        if cover_url:
            cover_source = "local"
            logger.info("[compute_cover_info] episode_id=%s ✅ resolved cover_url from cover_path: %s", episode_id, cover_url)
        else:
            logger.warning("[compute_cover_info] episode_id=%s ❌ _cover_url_for returned None for cover_path: %s", episode_id, cover_path)
    
    # ALWAYS fall back to Spreaker remote_cover_url if nothing else works
    if not cover_url and remote_cover_url:
        logger.info("[compute_cover_info] episode_id=%s trying remote_cover_url: %s", episode_id, remote_cover_url)
        cover_url = _cover_url_for(remote_cover_url)
        if cover_url:
            cover_source = "remote"
            logger.info("[compute_cover_info] episode_id=%s ✅ resolved cover_url from remote_cover_url: %s", episode_id, cover_url)
        else:
            logger.warning("[compute_cover_info] episode_id=%s ❌ _cover_url_for returned None for remote_cover_url: %s", episode_id, remote_cover_url)
    
    if not cover_url:
        logger.warning(
            "[compute_cover_info] episode_id=%s ❌ NO cover URL resolved! gcs_cover_path=%s cover_path=%s remote_cover_url=%s status=%s",
            episode_id, 
            gcs_cover_path[:100] + "..." if gcs_cover_path and len(str(gcs_cover_path)) > 100 else gcs_cover_path,
            cover_path,
            remote_cover_url,
            status_str
        )
    
    return {
        "cover_url": cover_url,
        "cover_source": cover_source,
        "within_7day_window": within_7days,
    }


__all__ = [
    "_final_url_for",
    "_cover_url_for",
    "_status_value",
    "compute_playback_info",
    "compute_cover_info",
]
