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
        
        # R2 URL (https://) - redirect directly
        if gcs_cover_str.lower().startswith(("http://", "https://")):
            # Reject Spreaker URLs
            if "spreaker.com" not in gcs_cover_str.lower() and "cdn.spreaker.com" not in gcs_cover_str.lower():
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
    
    # If cover_path is a URL, redirect to it
    if cover_path_str.lower().startswith(("http://", "https://")):
        # Reject Spreaker URLs
        if "spreaker.com" not in cover_path_str.lower() and "cdn.spreaker.com" not in cover_path_str.lower():
            return RedirectResponse(url=cover_path_str, status_code=302)
    
    # Try to serve local file
    candidates = []
    p = Path(cover_path_str)
    candidates.append(p)
    
    # Workspace root and media_uploads fallbacks
    if not p.is_absolute():
        candidates.append(WS_ROOT / cover_path_str)
        candidates.append(MEDIA_DIR / cover_path_str.lstrip("/\\"))
    
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
    
    raise HTTPException(status_code=404, detail="Cover file missing on disk")
