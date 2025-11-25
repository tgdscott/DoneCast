import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from sqlalchemy import or_, and_

from api.core.paths import FINAL_DIR, MEDIA_DIR
from api.models.podcast import EpisodeStatus


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
        gcs_path: GCS path (gs://...), R2 path (r2://...), or R2 URL (https://...) if available
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
    
    # Priority 1a: R2 path (r2://bucket/key) - generate signed URL
    if gcs_path and str(gcs_path).startswith("r2://"):
        try:
            from infrastructure.r2 import generate_signed_url
            r2_str = str(gcs_path)[5:]  # Remove "r2://"
            parts = r2_str.split("/", 1)
            if len(parts) == 2:
                bucket, key = parts
                url = generate_signed_url(bucket, key, expiration=86400)  # 24hr expiry
                if url:
                    return url
        except Exception as e:
            from api.core.logging import get_logger
            logger = get_logger("api.episodes.common")
            logger.warning("R2 URL generation failed for %s: %s", gcs_path, e)
            # Fall through to path-based resolution
    
    # Priority 1b: R2 URL (https://) - generate signed URL (R2 buckets are NOT public by default)
    # BUT reject Spreaker URLs (push-only relationship)
    if gcs_path and str(gcs_path).lower().startswith(("http://", "https://")):
        gcs_path_str = str(gcs_path).lower()
        # CRITICAL: Reject Spreaker URLs - we have a push-only relationship
        if "spreaker.com" in gcs_path_str or "cdn.spreaker.com" in gcs_path_str:
            from api.core.logging import get_logger
            logger = get_logger("api.episodes.common")
            logger.warning("Rejecting Spreaker URL in gcs_path: %s", str(gcs_path)[:100])
            return None
        # R2 URLs need signed URLs - parse and generate presigned URL
        if ".r2.cloudflarestorage.com" in gcs_path_str:
            try:
                import os
                from urllib.parse import unquote
                from infrastructure.r2 import generate_signed_url
                
                # Remove protocol
                url_without_proto = str(gcs_path).replace("https://", "").replace("http://", "")
                # Split on first slash to separate host from path
                if "/" in url_without_proto:
                    host_part, key_part = url_without_proto.split("/", 1)
                    # Extract bucket name (first part before first dot)
                    bucket_name = host_part.split(".")[0]
                    # URL-decode the key
                    key = unquote(key_part)
                    # Generate signed URL (24 hour expiration for covers)
                    signed_url = generate_signed_url(bucket_name, key, expiration=86400)
                    if signed_url:
                        return signed_url
            except Exception as e:
                from api.core.logging import get_logger
                logger = get_logger("api.episodes.common")
                logger.warning("Failed to generate signed URL for R2 cover: %s", e)
                # Fall through to return original URL as fallback (may not work if bucket is private)
        # For other HTTPS URLs (non-R2, non-Spreaker), return as-is
        return str(gcs_path)
    
    # Priority 2: Check path for GCS/R2 paths (legacy episodes may have gs:// or r2:// in cover_path)
    if path:
        p = str(path)
        # Handle GCS paths (gs://) in cover_path field
        if p.startswith("gs://"):
            try:
                from infrastructure.gcs import get_signed_url
                gcs_str = p[5:]  # Remove "gs://"
                parts = gcs_str.split("/", 1)
                if len(parts) == 2:
                    bucket, key = parts
                    url = get_signed_url(bucket, key, expiration=3600)
                    if url:
                        return url
            except Exception as e:
                from api.core.logging import get_logger
                logger = get_logger("api.episodes.common")
                logger.warning("GCS URL generation failed for cover_path %s: %s", p[:100], e)
                # Fall through to other checks
        
        # Handle R2 paths (r2://) in cover_path field
        if p.startswith("r2://"):
            try:
                from infrastructure.r2 import generate_signed_url
                r2_str = p[5:]  # Remove "r2://"
                parts = r2_str.split("/", 1)
                if len(parts) == 2:
                    bucket, key = parts
                    url = generate_signed_url(bucket, key, expiration=86400)  # 24hr expiry
                    if url:
                        return url
            except Exception as e:
                from api.core.logging import get_logger
                logger = get_logger("api.episodes.common")
                logger.warning("R2 URL generation failed for cover_path %s: %s", p[:100], e)
                # Fall through to other checks
        
        # Handle R2 HTTPS URLs in cover_path field
        if p.lower().startswith(("http://", "https://")):
            # CRITICAL: Reject Spreaker URLs - we have a push-only relationship
            if "spreaker.com" in p.lower() or "cdn.spreaker.com" in p.lower():
                from api.core.logging import get_logger
                logger = get_logger("api.episodes.common")
                logger.warning("Rejecting Spreaker URL in cover_path: %s", p[:100])
                return None
            # Handle R2 URLs - generate signed URL
            if ".r2.cloudflarestorage.com" in p.lower():
                try:
                    import os
                    from urllib.parse import unquote
                    from infrastructure.r2 import generate_signed_url
                    
                    # Remove protocol
                    url_without_proto = p.replace("https://", "").replace("http://", "")
                    # Split on first slash to separate host from path
                    if "/" in url_without_proto:
                        host_part, key_part = url_without_proto.split("/", 1)
                        # Extract bucket name (first part before first dot)
                        bucket_name = host_part.split(".")[0]
                        # URL-decode the key
                        key = unquote(key_part)
                        # Generate signed URL (24 hour expiration for covers)
                        signed_url = generate_signed_url(bucket_name, key, expiration=86400)
                        if signed_url:
                            return signed_url
                except Exception as e:
                    from api.core.logging import get_logger
                    logger = get_logger("api.episodes.common")
                    logger.warning("Failed to generate signed URL for R2 cover_path: %s", e)
            # For other HTTPS URLs (non-R2, non-Spreaker), return as-is
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


def compute_playback_info(episode: Any, *, now: Optional[datetime] = None, wrap_with_op3: bool = False) -> dict[str, Any]:
    """Determine playback URL from R2/GCS or Spreaker.

    Priority order for audio URLs:
    1. R2/GCS URL (gcs_audio_path) - Primary storage for YOUR episodes
    2. Spreaker stream URL - For Spreaker-hosted episodes

    NO LOCAL FILES - cloud storage or Spreaker only.
    
    Args:
        episode: Episode object
        now: Optional datetime for testing
        wrap_with_op3: If True, wrap audio URL with OP3 prefix for tracking (default: False)
    
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
    
    # Wrap with OP3 prefix if requested (for public website tracking)
    if wrap_with_op3 and playback_url:
        try:
            # Import OP3 wrapper function from services module
            from api.services.op3_analytics import wrap_url_with_op3
            playback_url = wrap_url_with_op3(str(playback_url))
        except Exception as err:
            from api.core.logging import get_logger
            logger = get_logger("api.episodes.common")
            logger.warning("Failed to wrap audio URL with OP3: %s", err)
            # Continue with unwrapped URL if OP3 wrapping fails
    
    playback_type = "cloud" if final_audio_url else ("spreaker" if stream_url else "none")
    audio_available = bool(cloud_exists or stream_url)

    return {
        "final_audio_url": final_audio_url,  # Cloud storage URL or None (unwrapped)
        "stream_url": stream_url,  # Spreaker stream or None
        "playback_url": playback_url,  # The actual URL to use (may be OP3-wrapped)
        "playback_type": playback_type,  # "cloud", "spreaker", or "none"
        "final_audio_exists": audio_available,  # True if any audio source exists
        "gcs_exists": cloud_exists,  # True if cloud file exists (legacy key name)
        "prefer_remote_audio": False,  # Deprecated
    }


def compute_cover_info(episode: Any, *, now: Optional[datetime] = None) -> dict[str, Any]:
    """Determine cover URL from R2/GCS, local, or remote sources.

    Priority order for cover URLs:
    1. R2/GCS URL (gcs_cover_path) - permanent storage
    2. Local file (cover_path) - for legacy episodes
    3. Remote URL (cover_path if HTTPS) - for migrated episodes

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
    
    # Debug logging for cover resolution (DEBUG level to reduce log spam)
    from api.core.logging import get_logger
    logger = get_logger("api.episodes.common")
    logger.debug(
        "[compute_cover_info] episode_id=%s status=%s gcs_cover_path=%s cover_path=%s remote_cover_url=%s",
        episode_id, status_str, 
        gcs_cover_path[:100] + "..." if gcs_cover_path and len(str(gcs_cover_path)) > 100 else gcs_cover_path,
        cover_path, 
        remote_cover_url
    )
    
    # Build cover URL based on priority
    cover_url = None
    cover_source = "none"
    
    # Try gcs_cover_path (R2 or GCS) - ALWAYS use if available (no retention window)
    if gcs_cover_path:
        gcs_cover_str = str(gcs_cover_path).strip()
        if gcs_cover_str:  # Only process non-empty strings
            is_r2_url = gcs_cover_str.lower().startswith(("http://", "https://"))
            
            logger.debug(
                "[compute_cover_info] episode_id=%s evaluating gcs_cover_path: is_r2_url=%s",
                episode_id, is_r2_url
            )
            
            # Always use gcs_cover_path if available (no retention restrictions)
            cover_url = _cover_url_for(None, gcs_path=gcs_cover_path)
            if cover_url:
                cover_source = "r2" if is_r2_url else "gcs"
                logger.debug(
                    "[compute_cover_info] episode_id=%s ✅ resolved cover_url from gcs_cover_path: %s (source=%s)",
                    episode_id, cover_url[:100] + "..." if len(cover_url) > 100 else cover_url, cover_source
                )
            else:
                logger.error(
                    "[compute_cover_info] episode_id=%s ❌ CRITICAL: _cover_url_for returned None for gcs_cover_path=%s. "
                    "This should never happen for R2 URLs. Check _cover_url_for implementation.",
                    episode_id, gcs_cover_path[:100] + "..." if gcs_cover_path and len(str(gcs_cover_path)) > 100 else gcs_cover_path
                )
    
    # Try local/remote cover_path
    if not cover_url and cover_path:
        logger.debug("[compute_cover_info] episode_id=%s trying cover_path: %s", episode_id, cover_path)
        cover_path_str = str(cover_path)
        
        # Check if it's a GCS path (gs://) - handle before treating as local filename
        if cover_path_str.startswith("gs://"):
            logger.debug("[compute_cover_info] episode_id=%s cover_path is GCS path, generating signed URL", episode_id)
            cover_url = _cover_url_for(cover_path)
            if cover_url:
                cover_source = "gcs"
                logger.debug("[compute_cover_info] episode_id=%s ✅ resolved cover_url from cover_path (GCS): %s", episode_id, cover_url)
            else:
                logger.warning("[compute_cover_info] episode_id=%s ⚠️ GCS signed URL generation failed for cover_path: %s", episode_id, cover_path_str[:100])
        # Check if it's a URL (R2, HTTPS, etc.)
        elif cover_path_str.lower().startswith(("http://", "https://")):
            # It's a URL - let _cover_url_for handle it
            cover_url = _cover_url_for(cover_path)
            if cover_url:
                cover_source = "r2" if ".r2.cloudflarestorage.com" in cover_path_str.lower() else "remote"
                logger.debug("[compute_cover_info] episode_id=%s ✅ resolved cover_url from cover_path URL: %s", episode_id, cover_url)
        # Check if it's an R2 path (r2://)
        elif cover_path_str.startswith("r2://"):
            logger.debug("[compute_cover_info] episode_id=%s cover_path is R2 path, generating signed URL", episode_id)
            cover_url = _cover_url_for(cover_path)
            if cover_url:
                cover_source = "r2"
                logger.debug("[compute_cover_info] episode_id=%s ✅ resolved cover_url from cover_path (R2): %s", episode_id, cover_url)
        else:
            # It's a local filename - check if file exists locally first
            cover_url = _cover_url_for(cover_path)
            if cover_url:
                cover_source = "local"
                logger.debug("[compute_cover_info] episode_id=%s ✅ resolved cover_url from cover_path (local): %s", episode_id, cover_url)
            else:
                # Local file doesn't exist - try to find it in R2 as fallback
                # This handles episodes that haven't been migrated yet
                # NOTE: This R2 lookup is expensive (multiple HTTP calls), so it's only done as fallback
                logger.debug("[compute_cover_info] episode_id=%s local file not found, searching R2 for cover_path: %s", episode_id, cover_path)
                try:
                    import os
                    from infrastructure.r2 import blob_exists
                    user_id = getattr(episode, "user_id", None)
                    # Convert UUID to hex string if needed
                    if user_id:
                        user_id_str = user_id.hex if hasattr(user_id, 'hex') else str(user_id)
                    else:
                        user_id_str = None
                    r2_bucket = os.getenv("R2_BUCKET", "ppp-media").strip()
                    
                    if user_id_str and r2_bucket:
                        # Try multiple R2 paths where the cover might be
                        cover_filename = os.path.basename(cover_path_str)
                        episode_id_str = str(episode_id) if episode_id else None
                        r2_candidates = []
                        
                        # Build candidate paths (only if we have the necessary IDs)
                        if episode_id_str:
                            r2_candidates.extend([
                                f"covers/episode/{episode_id_str}/{cover_filename}",
                                f"{user_id_str}/episodes/{episode_id_str}/cover/{cover_filename}",
                            ])
                        if user_id_str:
                            r2_candidates.extend([
                                f"covers/{user_id_str}/{cover_filename}",
                                f"{user_id_str}/covers/{cover_filename}",
                            ])
                        
                        # Check each candidate (stop at first match to avoid unnecessary calls)
                        for r2_key in r2_candidates:
                            if blob_exists(r2_bucket, r2_key):
                                # Found in R2 - generate signed URL
                                from infrastructure.r2 import generate_signed_url
                                signed_url = generate_signed_url(r2_bucket, r2_key, expiration=86400)
                                if signed_url:
                                    cover_url = signed_url
                                    cover_source = "r2"
                                    logger.info("[compute_cover_info] episode_id=%s ✅ found cover in R2 at %s", episode_id, r2_key)
                                    break
                except Exception as r2_err:
                    logger.debug("[compute_cover_info] episode_id=%s R2 lookup failed: %s", episode_id, r2_err)
                
                if not cover_url:
                    logger.debug("[compute_cover_info] episode_id=%s ❌ cover_path not found locally or in R2: %s", episode_id, cover_path)
    
    # CRITICAL: Push-only relationship with Spreaker - NEVER use Spreaker URLs
    # DO NOT fall back to remote_cover_url - it contains Spreaker URLs which we never serve
    # Only use our own storage (gcs_cover_path or cover_path)
    if not cover_url and remote_cover_url:
        logger.warning(
            "[compute_cover_info] episode_id=%s ⚠️ Ignoring remote_cover_url (contains Spreaker URLs - push-only relationship): %s",
            episode_id,
            remote_cover_url[:100] if remote_cover_url else None
        )
    
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
    }


def is_published_condition(now: Optional[datetime] = None):
    """
    Returns a SQLAlchemy condition that matches episodes that are "published".
    
    An episode is considered "published" if:
    1. status == 'published' (explicitly published), OR
    2. status == 'processed' AND publish_at <= now (scheduled episode whose time has passed)
    
    This unifies the logic so publish_at is the source of truth for published status,
    eliminating the need for a maintenance job to update status when publish_at passes.
    
    Args:
        now: Current datetime (UTC). If None, uses datetime.now(timezone.utc)
    
    Returns:
        SQLAlchemy condition that can be used in .where() clauses
    
    Usage:
        from api.routers.episodes.common import is_published_condition
        from api.models.podcast import Episode
        episodes = session.exec(
            select(Episode).where(is_published_condition())
        ).all()
    """
    # Import here to avoid circular imports and ensure Episode is the SQLModel class
    from api.models.podcast import Episode
    
    if now is None:
        now = datetime.now(timezone.utc)
    
    # Build the condition using Episode model columns
    return or_(
        Episode.status == EpisodeStatus.published,
        and_(
            Episode.status == EpisodeStatus.processed,
            Episode.publish_at.isnot(None),
            Episode.publish_at <= now
        )
    )


__all__ = [
    "_final_url_for",
    "_cover_url_for",
    "_status_value",
    "compute_playback_info",
    "compute_cover_info",
    "is_published_condition",
]
