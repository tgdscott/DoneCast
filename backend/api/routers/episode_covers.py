import os
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pathlib import Path
from uuid import UUID

from api.core.database import get_session
from api.core import crud
from api.core.paths import WS_ROOT, MEDIA_DIR

router = APIRouter(prefix="/episodes", tags=["episodes"])

@router.get("/{episode_id}/cover")
def get_episode_cover(episode_id: str, session: Session = Depends(get_session)):
    """Get episode cover image.
    
    Priority:
    1. If gcs_cover_path is an R2 URL (https://), redirect to it
    2. If gcs_cover_path is a GCS URL (gs://), generate signed URL and redirect
    3. If cover_path is a local file, serve it
    4. Otherwise, 404
    """
    from fastapi.responses import RedirectResponse
    
    # look up episode
    try:
        ep = crud.get_episode_by_id(session, UUID(episode_id))
    except Exception:
        ep = None
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")
    
    # Priority 1: Check gcs_cover_path (R2 URLs or GCS URLs)
    gcs_cover_path = getattr(ep, "gcs_cover_path", None)
    if gcs_cover_path:
        gcs_cover_str = str(gcs_cover_path).strip()
        
        # R2 URL (https://) - generate signed URL (R2 buckets are NOT public by default)
        if gcs_cover_str.lower().startswith(("http://", "https://")):
            # Reject Spreaker URLs
            if "spreaker.com" not in gcs_cover_str.lower() and "cdn.spreaker.com" not in gcs_cover_str.lower():
                # Check if it's an R2 URL - if so, generate signed URL
                if ".r2.cloudflarestorage.com" in gcs_cover_str.lower():
                    try:
                        import os
                        from urllib.parse import unquote
                        from infrastructure.r2 import generate_signed_url
                        
                        # Remove protocol
                        url_without_proto = gcs_cover_str.replace("https://", "").replace("http://", "")
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
                                return RedirectResponse(url=signed_url, status_code=302)
                    except Exception as e:
                        from api.core.logging import get_logger
                        logger = get_logger("api.episode_covers")
                        logger.warning("Failed to generate signed URL for R2 cover: %s", e)
                        # Fall through to redirect to original URL (may not work if bucket is private)
                # For other HTTPS URLs (non-R2, non-Spreaker), redirect directly
                return RedirectResponse(url=gcs_cover_str, status_code=302)
        
        # GCS URL (gs://) - generate signed URL
        elif gcs_cover_str.startswith("gs://"):
            try:
                from infrastructure.gcs import get_signed_url
                gcs_str = gcs_cover_str[5:]  # Remove "gs://"
                parts = gcs_str.split("/", 1)
                if len(parts) == 2:
                    bucket, key = parts
                    signed_url = get_signed_url(bucket, key, expiration=3600)
                    if signed_url:
                        return RedirectResponse(url=signed_url, status_code=302)
            except Exception as e:
                from api.core.logging import get_logger
                logger = get_logger("api.episode_covers")
                logger.warning("Failed to generate signed URL for GCS cover: %s", e)
    
    # Priority 2: Check cover_path (local file or URL)
    cover_path = getattr(ep, "cover_path", None)
    if not cover_path:
        raise HTTPException(status_code=404, detail="Cover not found")
    
    cover_path_str = str(cover_path)
    
    # If cover_path is a URL, handle it
    if cover_path_str.lower().startswith(("http://", "https://")):
        # Reject Spreaker URLs
        if "spreaker.com" not in cover_path_str.lower() and "cdn.spreaker.com" not in cover_path_str.lower():
            # Check if it's an R2 URL - if so, generate signed URL
            if ".r2.cloudflarestorage.com" in cover_path_str.lower():
                try:
                    import os
                    from urllib.parse import unquote
                    from infrastructure.r2 import generate_signed_url
                    
                    # Remove protocol
                    url_without_proto = cover_path_str.replace("https://", "").replace("http://", "")
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
                            return RedirectResponse(url=signed_url, status_code=302)
                except Exception as e:
                    from api.core.logging import get_logger
                    logger = get_logger("api.episode_covers")
                    logger.warning("Failed to generate signed URL for R2 cover_path: %s", e)
            # For other HTTPS URLs (non-R2, non-Spreaker), redirect directly
            return RedirectResponse(url=cover_path_str, status_code=302)
    
    # Try to serve local file
    candidates = []
    p = Path(cover_path_str)
    candidates.append(p)
    
    # Workspace root and media_uploads fallbacks
    if not p.is_absolute():
        candidates.append(WS_ROOT / cover_path_str)
        candidates.append(MEDIA_DIR / cover_path_str.lstrip("/\\"))
        # Also try just the basename in MEDIA_DIR
        candidates.append(MEDIA_DIR / os.path.basename(cover_path_str))
    
    for cp in candidates:
        if cp.is_file():
            suf = cp.suffix.lower()
            mt = "image/jpeg"
            if suf == ".png":
                mt = "image/png"
            elif suf in (".jpg", ".jpeg"):
                mt = "image/jpeg"
            elif suf == ".webp":
                mt = "image/webp"
            return FileResponse(path=str(cp), media_type=mt)
    
    # Local file doesn't exist - try to find it in R2 as fallback
    # This handles episodes that haven't been migrated yet
    # NOTE: This R2 lookup is expensive (multiple HTTP calls), so it's only done as fallback
    try:
        from infrastructure.r2 import blob_exists, generate_signed_url
        user_id = getattr(ep, "user_id", None)
        # Convert UUID to hex string if needed
        if user_id:
            user_id_str = user_id.hex if hasattr(user_id, 'hex') else str(user_id)
        else:
            user_id_str = None
        episode_id_str = str(ep.id)
        r2_bucket = os.getenv("R2_BUCKET", "ppp-media").strip()
        
        if user_id_str and r2_bucket:
            # Try multiple R2 paths where the cover might be
            cover_filename = os.path.basename(cover_path_str)
            r2_candidates = [
                f"covers/episode/{episode_id_str}/{cover_filename}",
                f"{user_id_str}/episodes/{episode_id_str}/cover/{cover_filename}",
                f"covers/{user_id_str}/{cover_filename}",
                f"{user_id_str}/covers/{cover_filename}",
            ]
            
            # Check each candidate (stop at first match to avoid unnecessary calls)
            for r2_key in r2_candidates:
                if blob_exists(r2_bucket, r2_key):
                    # Found in R2 - generate signed URL and redirect
                    signed_url = generate_signed_url(r2_bucket, r2_key, expiration=86400)
                    if signed_url:
                        from api.core.logging import get_logger
                        logger = get_logger("api.episode_covers")
                        logger.info("Found cover in R2 at %s for episode %s", r2_key, episode_id_str)
                        return RedirectResponse(url=signed_url, status_code=302)
    except Exception as r2_err:
        from api.core.logging import get_logger
        logger = get_logger("api.episode_covers")
        logger.debug("R2 lookup failed for cover_path %s: %s", cover_path_str, r2_err)
    
    raise HTTPException(status_code=404, detail="Cover file missing on disk and not found in R2")
