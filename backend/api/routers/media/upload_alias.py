import os
import uuid
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi import status
from typing import Optional

from api.core.auth import get_current_user
from api.models.user import User
from api.core.paths import MEDIA_DIR

router = APIRouter(tags=["media"])

# MEDIA_DIR now centrally defined and created in api.core.paths

ALLOWED_CONTENT_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/webp": ".webp"}

@router.post("/media/upload/cover_art", status_code=status.HTTP_201_CREATED)
async def upload_cover_art(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),  # noqa: ARG001 (ensures auth)
):
    """Accept a cover image upload and persist it under media_uploads/ returning the stored filename.

    Frontend expects one of: filename | path | stored_as. We return all for flexibility.
    """
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported image type: {file.content_type}")
    # Derive extension from content type (prefer predictable normalized ext)
    ext = ALLOWED_CONTENT_TYPES[file.content_type]
    # Generate unique name
    base = f"cover_{uuid.uuid4().hex}{ext}"
    dest_path = MEDIA_DIR / base
    try:
        data = await file.read()
        if not data:
            raise HTTPException(status_code=400, detail="Empty file upload")
        with open(dest_path, "wb") as fh:
            fh.write(data)
    except HTTPException:
        raise
    except Exception as ex:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Failed to store image: {ex}")
    return {
        "filename": base,
        "stored_as": base,
        "path": base,
        "content_type": file.content_type,
        "size": len(data),
    }
