import os
import uuid
from pathlib import Path
from fastapi import APIRouter, UploadFile, HTTPException, Depends, Request
from fastapi import status

from api.routers.auth import get_current_user
from ..models.user import User
from api.core.paths import MEDIA_DIR

router = APIRouter(tags=["media"])

# MEDIA_DIR now centrally defined and created in api.core.paths

ALLOWED_CONTENT_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/webp": ".webp"}

@router.post("/api/media/upload/cover_art", status_code=status.HTTP_201_CREATED)
async def upload_cover_art(
    request: Request,

    current_user: User = Depends(get_current_user),  # noqa: ARG001 (ensures auth)
):
    """Accept a cover image upload and persist it under media_uploads/ returning the stored filename.

    Frontend expects one of: filename | path | stored_as. We return all for flexibility.
    """
    form = await request.form()

    def _coerce_upload(value):
        if isinstance(value, UploadFile):
            return value
        if isinstance(value, (list, tuple)):
            for item in value:
                if isinstance(item, UploadFile):
                    return item
        return None

    upload = None
    for key in ("file", "files", "cover", "cover_file", "file[]", "files[]"):
        if key not in form:
            continue
        candidate = _coerce_upload(form.get(key))
        if candidate is None and hasattr(form, "getlist"):
            candidate = _coerce_upload(form.getlist(key))
        if candidate is not None:
            upload = candidate
            break

    if upload is None and hasattr(form, "multi_items"):
        for _, value in form.multi_items():
            candidate = _coerce_upload(value)
            if candidate is not None:
                upload = candidate
                break

    if upload is None:
        raise HTTPException(status_code=400, detail="No cover image provided")
    if upload.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported image type: {upload.content_type}")
    # Derive extension from content type (prefer predictable normalized ext)
    ext = ALLOWED_CONTENT_TYPES[upload.content_type]
    # Generate unique name
    base = f"cover_{uuid.uuid4().hex}{ext}"
    dest_path = MEDIA_DIR / base
    try:
        data = await upload.read()
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
        "content_type": upload.content_type,
        "size": len(data),
    }
