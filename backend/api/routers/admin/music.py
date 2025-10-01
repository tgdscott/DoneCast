from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

import requests
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import Session, select

from api.core.database import get_session
from api.core.paths import MEDIA_DIR
from api.models.podcast import MusicAsset, MusicAssetSource
from api.models.user import User

from infrastructure.gcs import upload_bytes as gcs_upload_bytes
from infrastructure.gcs import upload_fileobj as gcs_upload_fileobj

from .deps import get_current_admin_user

router = APIRouter(prefix="/music/assets", tags=["Admin - Music"])


class MusicAssetPayload(BaseModel):
    display_name: str
    url: Optional[str] = None
    preview_url: Optional[str] = None
    mood_tags: Optional[list[str]] = None
    license: Optional[str] = None
    attribution: Optional[str] = None
    source_type: Optional[MusicAssetSource] = None


@router.get("/music/assets", status_code=200)
def admin_list_music_assets(
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
):
    del admin_user
    rows = session.exec(select(MusicAsset)).all()
    assets: list[dict[str, Any]] = []
    for asset in rows:
        try:
            tags = asset.mood_tags()
        except Exception:
            tags = []
        assets.append(
            {
                "id": str(asset.id),
                "display_name": asset.display_name,
                "filename": asset.filename,
                "url": asset.filename,
                "duration_s": asset.duration_s,
                "mood_tags": tags,
                "source_type": asset.source_type,
                "license": asset.license,
                "attribution": asset.attribution,
                "select_count": asset.user_select_count,
                "created_at": asset.created_at.isoformat() if getattr(asset, "created_at", None) else None,
            }
        )
    return {"assets": assets}


@router.post("/music/assets", status_code=201)
def admin_create_music_asset(
    payload: MusicAssetPayload,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
):
    del admin_user
    if not payload.display_name:
        raise HTTPException(status_code=400, detail="display_name is required")
    filename = (payload.url or "").strip()
    if not filename:
        raise HTTPException(status_code=400, detail="url is required")
    try:
        asset = MusicAsset(
            display_name=payload.display_name.strip(),
            filename=filename,
            mood_tags_json=json.dumps(payload.mood_tags or []),
            source_type=payload.source_type or MusicAssetSource.external,
            license=payload.license,
            attribution=payload.attribution,
        )
        session.add(asset)
        session.commit()
        session.refresh(asset)
        return {"id": str(asset.id)}
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create asset: {exc}")


@router.put("/music/assets/{asset_id}", status_code=200)
def admin_update_music_asset(
    asset_id: str,
    payload: MusicAssetPayload,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
):
    del admin_user
    try:
        key = UUID(str(asset_id))
    except Exception:
        raise HTTPException(status_code=404, detail="Asset not found")
    asset = session.get(MusicAsset, key)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    try:
        if payload.display_name is not None:
            asset.display_name = payload.display_name.strip()
        if payload.url is not None and payload.url.strip():
            asset.filename = payload.url.strip()
        if payload.mood_tags is not None:
            asset.mood_tags_json = json.dumps(payload.mood_tags)
        if payload.source_type is not None:
            asset.source_type = payload.source_type
        if payload.license is not None:
            asset.license = payload.license
        if payload.attribution is not None:
            asset.attribution = payload.attribution
        session.add(asset)
        session.commit()
        session.refresh(asset)
        return {"id": str(asset.id)}
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update asset: {exc}")


@router.delete("/music/assets/{asset_id}", status_code=200)
def admin_delete_music_asset(
    asset_id: str,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
):
    del admin_user
    try:
        key = UUID(str(asset_id))
    except Exception:
        raise HTTPException(status_code=404, detail="Asset not found")
    asset = session.get(MusicAsset, key)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    try:
        session.delete(asset)
        session.commit()
        return {"ok": True}
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete asset: {exc}")


def _sanitize_filename(name: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]", "_", (name or "").strip())
    return base or uuid.uuid4().hex


def _ensure_music_dir() -> Path:
    music_dir = MEDIA_DIR / "music"
    music_dir.mkdir(parents=True, exist_ok=True)
    return music_dir


def _unique_path(dirpath: Path, base: str) -> Path:
    candidate = dirpath / base
    if not candidate.exists():
        return candidate
    stem = Path(base).stem
    suf = Path(base).suffix
    for i in range(1, 10000):
        candidate = dirpath / f"{stem}-{i}{suf}"
        if not candidate.exists():
            return candidate
    return dirpath / f"{stem}-{uuid.uuid4().hex}{suf}"


@router.post("/music/assets/upload", status_code=201)
def admin_upload_music_asset(
    file: UploadFile = File(...),
    display_name: Optional[str] = Form(None),
    mood_tags: Optional[str] = Form(None),
    license: Optional[str] = Form(None),
    attribution: Optional[str] = Form(None),
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
):
    del admin_user
    try:
        original = file.filename or "uploaded.mp3"
        base = _sanitize_filename(original)
        if "." not in base:
            base += ".mp3"

        bucket = os.getenv("MEDIA_BUCKET")
        if bucket:
            key = f"music/{uuid.uuid4().hex}_{base}"
            stored_uri = gcs_upload_fileobj(
                bucket,
                key,
                file.file,
                content_type=(file.content_type or "audio/mpeg"),
            )
            filename_stored = (
                stored_uri if stored_uri.startswith("gs://") else f"/static/media/{Path(stored_uri).name}"
            )
        else:
            music_dir = _ensure_music_dir()
            out_path = _unique_path(music_dir, base)
            with out_path.open("wb") as output:
                shutil.copyfileobj(file.file, output)
            filename_stored = f"/static/media/music/{out_path.name}"

        if mood_tags:
            try:
                tags_list = json.loads(mood_tags)
                if not isinstance(tags_list, list):
                    raise ValueError
            except Exception:
                tags_list = [t.strip() for t in mood_tags.split(",") if t.strip()]
        else:
            tags_list = []

        asset = MusicAsset(
            display_name=(display_name or Path(original).stem),
            filename=filename_stored,
            mood_tags_json=json.dumps(tags_list or []),
            source_type=MusicAssetSource.external,
            license=license,
            attribution=attribution,
        )
        session.add(asset)
        session.commit()
        session.refresh(asset)
        return {"id": str(asset.id), "filename": filename_stored}
    except HTTPException:
        raise
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Upload failed: {exc}")


class MusicAssetImportUrl(BaseModel):
    display_name: str
    source_url: str
    mood_tags: Optional[list[str]] = None
    license: Optional[str] = None
    attribution: Optional[str] = None


@router.post("/music/assets/import-url", status_code=201)
def admin_import_music_asset_by_url(
    payload: MusicAssetImportUrl,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
):
    del admin_user
    url = (payload.source_url or "").strip()
    if not url or not (url.lower().startswith("http://") or url.lower().startswith("https://")):
        raise HTTPException(status_code=400, detail="source_url must be http(s)")
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        ext = None
        content_type = (response.headers.get("content-type", "") or "").lower()
        if "audio/" in content_type:
            ext = "." + content_type.split("/", 1)[-1].split(";")[0].strip()
            if ext == ".mpeg":
                ext = ".mp3"
        if not ext:
            try:
                from urllib.parse import urlparse

                parsed = Path(urlparse(url).path)
                ext = parsed.suffix or ".mp3"
            except Exception:
                ext = ".mp3"
        safe_name = _sanitize_filename((payload.display_name or "track") + ext)

        bucket = os.getenv("MEDIA_BUCKET")
        if bucket:
            key = f"music/{uuid.uuid4().hex}_{safe_name}"
            content = response.content
            stored_uri = gcs_upload_bytes(bucket, key, content, content_type=(content_type or "audio/mpeg"))
            filename_stored = (
                stored_uri if stored_uri.startswith("gs://") else f"/static/media/{Path(stored_uri).name}"
            )
        else:
            music_dir = _ensure_music_dir()
            out_path = _unique_path(music_dir, safe_name)
            with out_path.open("wb") as output:
                shutil.copyfileobj(response.raw, output)
            filename_stored = f"/static/media/music/{out_path.name}"

        asset = MusicAsset(
            display_name=payload.display_name.strip(),
            filename=filename_stored,
            mood_tags_json=json.dumps(payload.mood_tags or []),
            source_type=MusicAssetSource.external,
            license=payload.license,
            attribution=payload.attribution,
        )
        session.add(asset)
        session.commit()
        session.refresh(asset)
        return {"id": str(asset.id), "filename": filename_stored}
    except HTTPException:
        raise
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Import failed: {exc}")


__all__ = ["router"]
