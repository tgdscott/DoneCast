import mimetypes
import os
import logging
from io import BytesIO
from typing import Optional, Sequence
import httpx

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select, col

from api.routers.auth import get_current_user
from api.core.database import get_session
from api.core.paths import MEDIA_DIR
from api.models.podcast import MusicAsset
from api.models.user import User
from infrastructure import storage
from infrastructure.gcs import make_signed_url, download_bytes as gcs_download_bytes
from infrastructure.r2 import generate_signed_url as r2_generate_signed_url

log = logging.getLogger(__name__)

router = APIRouter(prefix="/music", tags=["music"])

@router.get("/assets")
def list_music_assets(
    request: Request, 
    session: Session = Depends(get_session), 
    mood: Optional[str] = None,
    scope: Optional[str] = None,  # 'global', 'user', or None (all)
    current_user: User = Depends(get_current_user)
) -> dict:
    query = select(MusicAsset)
    
    # Filter by scope
    if scope == "global":
        query = query.where(MusicAsset.is_global == True)
    elif scope == "user":
        query = query.where(MusicAsset.owner_id == current_user.id)
    else:
        # Return both global and user's own music
        query = query.where(
            (MusicAsset.is_global == True) | (MusicAsset.owner_id == current_user.id)
        )
    
    # Sort: user's own music first, then global music (alphabetically by display_name within each group)
    # is_global=False (user music) comes before is_global=True (global music)
    query = query.order_by(col(MusicAsset.is_global).asc(), col(MusicAsset.display_name).asc())
    
    assets: Sequence[MusicAsset] = session.exec(query).all()
    out = []
    for a in assets:
        try:
            tags = a.mood_tags()
        except Exception:
            tags = []
        if mood and mood not in tags:
            continue
        # Build a preview URL for browser playback.
        # - If gs://, generate a signed URL (dev shim returns /static path)
        # - If http(s), use as-is
        # - Otherwise treat as local path relative to /static/media
        filename = a.filename or ""
        filename_url = filename
        file_exists = True
        
        # Handle GCS paths (gs://bucket/key)
        if filename.startswith("gs://"):
            try:
                without = filename[len("gs://"):]
                bucket, key = without.split("/", 1)
                signed_url = make_signed_url(bucket, key, minutes=60)
                # Check if we got a proper signed URL (contains signature query params)
                # Public URLs without signatures may not work due to CORS, so use proxy endpoint instead
                if signed_url and "?" in signed_url:
                    # Check if it has signature-related query parameters (X-Goog-* params indicate signed URL)
                    query_part = signed_url.split("?", 1)[1]
                    has_signature = any(
                        param.startswith("X-Goog-") for param in query_part.split("&")
                    )
                    if has_signature:
                        # Valid signed URL - use it
                        filename_url = signed_url
                    else:
                        # Public URL without proper signature - use proxy endpoint for reliability
                        filename_url = str(request.url_for("preview_music_asset", asset_id=str(a.id)))
                elif signed_url and signed_url.startswith("https://storage.googleapis.com/") and "?" not in signed_url:
                    # Public URL without any query params - use proxy endpoint for reliability
                    filename_url = str(request.url_for("preview_music_asset", asset_id=str(a.id)))
                elif signed_url:
                    # Some other URL format (e.g., local dev path like /static/media/...) - try using it
                    filename_url = signed_url
                else:
                    # No URL returned - use proxy endpoint
                    filename_url = str(request.url_for("preview_music_asset", asset_id=str(a.id)))
                file_exists = True
            except Exception as e:
                log.warning(f"[music/list] Failed to generate signed URL for {filename}: {e}")
                # Fallback: proxy through API so the client gets an http(s) URL
                filename_url = str(request.url_for("preview_music_asset", asset_id=str(a.id)))
                file_exists = True
        
        # CRITICAL: R2 paths are NOT SUPPORTED for music files
        # Music files MUST be in GCS because they are used during episode construction
        # Only final production-ready episodes go to R2 (distribution files)
        # If we see an r2:// path, it's a data integrity error
        elif filename.startswith("r2://"):
            log.error(
                f"[music/list] DATA INTEGRITY ERROR: Music asset {a.id} has R2 path '{filename}'. "
                "Music files MUST be stored in GCS (not R2) because they are used in episode construction. "
                "Only final production-ready episodes go to R2."
            )
            # Fallback to proxy endpoint (which will also error, but provides better error message)
            filename_url = str(request.url_for("preview_music_asset", asset_id=str(a.id)))
            file_exists = False  # Mark as not existing since it's in wrong storage
        
        # Handle HTTP/HTTPS URLs (already public/signed)
        elif filename.startswith('http://') or filename.startswith('https://'):
            filename_url = filename
            file_exists = True
        else:
            # Normalize leading slash and build absolute URL so the React dev server (5173) doesn't try to serve it.
            rel = filename.lstrip('/')
            if not rel.startswith('static/media'):
                rel = f"static/media/{rel}"
            base = str(request.base_url).rstrip('/')
            filename_url = f"{base}/{rel}"
            try:
                if 'static/media/' in filename_url:
                    rel2 = filename_url.split('/static/media/', 1)[-1]
                    file_exists = (MEDIA_DIR / rel2).is_file()
            except Exception:
                file_exists = True
        out.append({
            "id": str(a.id),
            "display_name": a.display_name,
            "filename": a.filename,
            "url": a.filename,  # raw stored value for admin editing convenience
            "preview_url": filename_url,
            "exists": file_exists,
            "duration_s": a.duration_s,
            "mood_tags": tags,
            "source_type": a.source_type,
            "license": a.license,
            "attribution": a.attribution,
            "select_count": a.user_select_count,
            "is_global": a.is_global,
            "owner_id": str(a.owner_id) if a.owner_id else None,
        })
    return {"assets": out}

@router.post("/assets/{asset_id}/select")
def register_music_selection(asset_id: str,
                             session: Session = Depends(get_session),
                             current_user: User = Depends(get_current_user)):
    asset = session.exec(select(MusicAsset).where(MusicAsset.id == asset_id)).first()
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Music asset not found")
    asset.user_select_count += 1
    session.add(asset)
    session.commit()
    session.refresh(asset)
    return {"id": str(asset.id), "select_count": asset.user_select_count}


@router.get("/assets/{asset_id}/preview")
def preview_music_asset(
    asset_id: str,
    session: Session = Depends(get_session),
):
    """Preview music asset by streaming from storage.
    
    CRITICAL: Music files are ALWAYS stored in GCS (not R2) because they are used
    in the production/construction of episodes. Only production-ready final files go to R2.
    
    Supports: GCS (gs://), HTTP/HTTPS URLs, or local files (dev only).
    """
    asset = session.exec(select(MusicAsset).where(MusicAsset.id == asset_id)).first()
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Music asset not found")

    filename = asset.filename or ""
    data: Optional[bytes] = None

    try:
        # CRITICAL: Music files MUST be in GCS, not R2
        # Music is used in episode construction, so it belongs in GCS (production files)
        # Only final, production-ready episodes go to R2 (distribution files)
        
        # Handle GCS paths (gs://bucket/key) - PRIMARY STORAGE FOR MUSIC
        if filename.startswith("gs://"):
            without = filename[len("gs://"):]
            try:
                bucket, key = without.split("/", 1)
                log.debug(f"[music/preview] Downloading from GCS: gs://{bucket}/{key}")
                # Use GCS download directly to ensure we use the bucket from the URL
                # storage.download_bytes ignores the bucket argument and uses the configured default
                data = gcs_download_bytes(bucket, key, force_gcs=True)
                if not data:
                    log.warning(f"[music/preview] GCS download returned None for gs://{bucket}/{key}")
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid GCS path format: {filename}"
                )
        
        # R2 paths are NOT SUPPORTED for music files
        # If we see an r2:// path, it's a data integrity error - music should be in GCS
        elif filename.startswith("r2://"):
            log.error(
                f"[music/preview] DATA INTEGRITY ERROR: Music asset {asset_id} has R2 path '{filename}'. "
                "Music files MUST be stored in GCS (not R2) because they are used in episode construction. "
                "Only final production-ready episodes go to R2."
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Music asset incorrectly stored in R2. Music files must be in GCS."
            )
        
        # Handle HTTP/HTTPS URLs
        elif filename.startswith("http://") or filename.startswith("https://"):
            log.debug(f"[music/preview] Downloading from HTTP(S): {filename[:80]}...")
            try:
                with httpx.Client(timeout=30.0, follow_redirects=True) as client:
                    response = client.get(filename)
                    response.raise_for_status()
                    data = response.content
                    if not data:
                        log.warning(f"[music/preview] HTTP download returned empty content from {filename[:80]}...")
            except httpx.HTTPError as e:
                log.error(f"[music/preview] HTTP download failed: {e}")
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Failed to download from URL: {str(e)}"
                )
        
        # Handle local files
        else:
            rel = filename.lstrip("/")
            if rel.startswith("static/media/"):
                rel = rel.split("static/media/", 1)[-1]
            path_obj = (MEDIA_DIR / rel).resolve()
            
            # Security check: ensure path is within MEDIA_DIR
            try:
                path_obj.resolve().relative_to(MEDIA_DIR.resolve())
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Invalid file path"
                )
            
            if not path_obj.is_file():
                log.warning(f"[music/preview] Local file not found: {path_obj}")
                raise FileNotFoundError(str(path_obj))
            
            log.debug(f"[music/preview] Reading local file: {path_obj}")
            data = path_obj.read_bytes()
    
    except FileNotFoundError:
        log.error(f"[music/preview] File not found: {filename}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Music asset file not found"
        )
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as exc:
        log.error(f"[music/preview] Unexpected error loading music asset: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to load music asset: {exc}"
        )

    if not data:
        log.error(f"[music/preview] No data returned for asset {asset_id} (filename: {filename[:80]}...)")
        # File doesn't exist in storage - return 404 instead of 502
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Music asset file not found in storage"
        )

    log.debug(f"[music/preview] Successfully loaded {len(data)} bytes for asset {asset_id}")
    guessed, _ = mimetypes.guess_type(filename)
    media_type = guessed or "audio/mpeg"
    return StreamingResponse(BytesIO(data), media_type=media_type)
