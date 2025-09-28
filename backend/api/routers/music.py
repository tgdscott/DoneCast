from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select, Session
from typing import List, Optional, Sequence
from api.core.database import get_session
from api.core.auth import get_current_user
from api.models.user import User
from api.models.podcast import MusicAsset
import os
from fastapi import Request
from api.core.paths import MEDIA_DIR
from infrastructure.gcs import make_signed_url

router = APIRouter(prefix="/music", tags=["music"])

@router.get("/assets")
def list_music_assets(request: Request, session: Session = Depends(get_session), mood: Optional[str] = None) -> dict:
    query = select(MusicAsset)
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
        if filename.startswith("gs://"):
            try:
                # Signed URL for direct playback; dev returns /static/media/<name>
                # Extract bucket/key for display only if needed by clients
                without = filename[len("gs://"):]
                bucket, key = without.split("/", 1)
                filename_url = make_signed_url(bucket, key, minutes=60)
                file_exists = True
            except Exception:
                # Fallback: report original value
                filename_url = filename
                file_exists = True
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
