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
    """Generate cover URL with priority: GCS > remote > local.
    
    Args:
        path: Local path or remote URL (legacy)
        gcs_path: GCS path (gs://...) if available
    """
    # Priority 1: GCS URL (survives container restarts)
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
    """Determine playback preference between local and Spreaker audio.

    Priority order for audio URLs:
    1. GCS URL (gcs_audio_path) - survives container restarts
    2. Local file (final_audio_path) - dev only
    3. Spreaker stream URL - published episodes

    Applies a 7-day grace period after publish where local audio remains the
    primary source, unless the local asset is missing. Returns keys compatible
    with existing episode serializers.
    """

    now_utc = _as_utc(now) or datetime.now(timezone.utc)
    
    # Priority 1: Check GCS URL (survives container restarts)
    gcs_audio_path = getattr(episode, "gcs_audio_path", None)
    final_audio_url = None
    local_final_exists = False
    
    if gcs_audio_path and str(gcs_audio_path).startswith("gs://"):
        try:
            from infrastructure.gcs import get_signed_url
            # Parse gs://bucket/key format
            gcs_str = str(gcs_audio_path)[5:]  # Remove "gs://"
            parts = gcs_str.split("/", 1)
            if len(parts) == 2:
                bucket, key = parts
                final_audio_url = get_signed_url(bucket, key, expiration=3600)
                local_final_exists = True  # Treat GCS as "available"
        except Exception:
            pass  # Fall back to local file check
    
    # Priority 2: Check local file (dev mode)
    if not final_audio_url:
        final_path = getattr(episode, "final_audio_path", None)
        local_candidates = _local_final_candidates(final_path)
        for cand in local_candidates:
            try:
                if cand.is_file():
                    local_final_exists = True
                    final_audio_url = _final_url_for(final_path)
                    break
            except Exception:
                continue

    stream_url = None
    try:
        spk_id = getattr(episode, "spreaker_episode_id", None)
        if spk_id:
            stream_url = f"https://api.spreaker.com/v2/episodes/{spk_id}/play"
    except Exception:
        stream_url = None

    status_str = _status_value(getattr(episode, "status", None))
    publish_at = _as_utc(getattr(episode, "publish_at", None))
    processed_at = _as_utc(getattr(episode, "processed_at", None))
    is_published_flag = bool(getattr(episode, "is_published_to_spreaker", False)) or status_str == "published"

    meta_force_local = False
    meta_force_remote = False
    remote_first_seen = None
    try:
        meta = json.loads(getattr(episode, "meta_json", "{}") or "{}")
        spreaker_meta = meta.get("spreaker") or {}
        if isinstance(spreaker_meta, dict):
            meta_force_local = bool(spreaker_meta.get("force_local_audio"))
            meta_force_remote = bool(spreaker_meta.get("force_remote_audio"))
            remote_first_seen = _parse_iso_datetime(spreaker_meta.get("remote_audio_first_seen"))
    except Exception:
        pass

    prefer_remote = False
    if stream_url and not meta_force_local:
        if meta_force_remote:
            prefer_remote = True
        elif not local_final_exists:
            prefer_remote = True
        else:
            # Respect scheduling: do not use remote audio before publish time.
            if publish_at and publish_at > now_utc:
                prefer_remote = False
            else:
                if is_published_flag:
                    reference = publish_at or remote_first_seen or processed_at
                    if reference and now_utc - reference >= timedelta(days=7):
                        prefer_remote = True
                # If publish metadata unavailable, fall back to local unless missing.

    playback_url = final_audio_url
    playback_type = "local" if final_audio_url else "none"

    if stream_url and (prefer_remote or (not final_audio_url and stream_url)):
        playback_url = stream_url
        playback_type = "stream"

    audio_available = local_final_exists or playback_type == "stream"

    return {
        "final_audio_url": final_audio_url,
        "stream_url": stream_url,
        "playback_url": playback_url,
        "playback_type": playback_type,
        "final_audio_exists": audio_available,
        "local_final_exists": local_final_exists,
        "prefer_remote_audio": playback_type == "stream" and stream_url is not None,
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
    
    # Try GCS first within 7-day window
    if within_7days and gcs_cover_path:
        cover_url = _cover_url_for(None, gcs_path=gcs_cover_path)
        if cover_url:
            cover_source = "gcs"
    
    # Try local/remote cover_path
    if not cover_url and cover_path:
        cover_url = _cover_url_for(cover_path)
        if cover_url:
            cover_source = "local"
    
    # ALWAYS fall back to Spreaker remote_cover_url if nothing else works
    if not cover_url and remote_cover_url:
        cover_url = _cover_url_for(remote_cover_url)
        if cover_url:
            cover_source = "remote"
    
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
