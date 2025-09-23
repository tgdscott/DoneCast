from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlmodel import Session, select
from typing import List, Optional
import logging
import requests
import io
from uuid import uuid4
from pathlib import Path

from api.core.database import get_session
from api.models.user import User
from api.routers.auth import get_current_user
from api.models.podcast import MusicAsset, MusicAssetCreate, MusicAssetPublic
from api.core.paths import MEDIA_DIR
from infrastructure.gcs import upload_fileobj, _require_bucket

log = logging.getLogger(__name__)
router = APIRouter(prefix="/music/assets", tags=["Admin - Music"])


def _require_admin(current_user: User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    return current_user


@router.get("/", response_model=dict)
def get_music_assets(session: Session = Depends(get_session), admin: User = Depends(_require_admin)):
    assets = session.exec(select(MusicAsset)).all()
    return {"assets": assets}


@router.post("/upload", response_model=MusicAssetPublic, status_code=status.HTTP_201_CREATED)
async def upload_music_asset(
    file: UploadFile = File(...),
    display_name: Optional[str] = Form(None),
    mood_tags: Optional[str] = Form(None), # JSON string
    session: Session = Depends(get_session),
    admin: User = Depends(_require_admin),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="File has no name")

    bucket = _require_bucket()
    safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in Path(file.filename).name)
    gcs_key = f"music/{uuid4().hex}_{safe_name}"

    try:
        gcs_uri = upload_fileobj(bucket, gcs_key, file.file, content_type=file.content_type or "audio/mpeg")
    except Exception as e:
        log.exception("Music upload to GCS failed")
        raise HTTPException(status_code=500, detail=f"File upload failed: {e}")

    tags = []
    if mood_tags:
        try:
            tags = json.loads(mood_tags)
            if not isinstance(tags, list):
                tags = []
        except Exception:
            pass

    asset = MusicAsset(
        display_name=display_name or Path(file.filename).stem,
        url=gcs_uri,
        preview_url=gcs_uri,
        mood_tags=tags,
        filename=gcs_key,
    )
    session.add(asset)
    session.commit()
    session.refresh(asset)
    return asset


class ImportUrlPayload(MusicAssetCreate):
    source_url: str

@router.post("/import-url", response_model=MusicAssetPublic, status_code=status.HTTP_201_CREATED)
def import_music_from_url(
    payload: ImportUrlPayload,
    session: Session = Depends(get_session),
    admin: User = Depends(_require_admin),
):
    try:
        with requests.get(payload.source_url, stream=True, timeout=30) as r:
            r.raise_for_status()
            content_type = r.headers.get("content-type", "audio/mpeg")
            # Use a memory buffer to stream the download to GCS
            file_obj = io.BytesIO(r.content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to download from URL: {e}")

    bucket = _require_bucket()
    safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in Path(payload.source_url).name)
    gcs_key = f"music/{uuid4().hex}_{safe_name}"

    try:
        gcs_uri = upload_fileobj(bucket, gcs_key, file_obj, content_type=content_type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File upload failed after download: {e}")

    asset = MusicAsset(
        display_name=payload.display_name or Path(payload.source_url).stem,
        url=gcs_uri,
        preview_url=gcs_uri,
        mood_tags=payload.mood_tags,
        filename=gcs_key,
    )
    session.add(asset)
    session.commit()
    session.refresh(asset)
    return asset


@router.put("/{asset_id}", response_model=MusicAssetPublic)
def update_music_asset(asset_id: int, payload: MusicAssetCreate, session: Session = Depends(get_session), admin: User = Depends(_require_admin)):
    asset = session.get(MusicAsset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    asset.display_name = payload.display_name
    asset.mood_tags = payload.mood_tags
    session.add(asset)
    session.commit()
    session.refresh(asset)
    return asset


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_music_asset(asset_id: int, session: Session = Depends(get_session), admin: User = Depends(_require_admin)):
    asset = session.get(MusicAsset, asset_id)
    if asset:
        session.delete(asset)
        session.commit()
    return None