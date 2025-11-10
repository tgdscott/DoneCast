import os
import uuid
import logging
from fastapi import APIRouter, UploadFile, HTTPException, Depends, status
from fastapi import Request
from io import BytesIO

from api.routers.auth import get_current_user
from ..models.user import User

router = APIRouter(tags=["media"])

logger = logging.getLogger("api.media_upload_alias")

ALLOWED_CONTENT_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/webp": ".webp"}
MAX_COVER_SIZE = 10 * 1024 * 1024  # 10 MB

@router.post("/media/upload/cover_art", status_code=status.HTTP_201_CREATED)
async def upload_cover_art(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """Accept a cover image upload and upload it to R2 cloud storage.
    
    Returns R2 URL that can be stored in episode cover_image_path or gcs_cover_path.
    Frontend expects one of: filename | path | stored_as. We return R2 URL in all fields.
    
    Accepts file uploads via any of these form field names: file, files, cover, cover_file
    """
    logger.info(f"Cover upload request received from user {current_user.id}")
    content_type_header = request.headers.get("content-type", "")
    logger.debug(f"Request Content-Type: {content_type_header}")
    
    # Parse form data manually
    try:
        form = await request.form()
        logger.debug(f"Form parsed. Keys: {list(form.keys()) if hasattr(form, 'keys') else 'N/A'}")
    except Exception as form_error:
        logger.error(f"Failed to parse form data: {form_error}", exc_info=True)
        raise HTTPException(
            status_code=400, 
            detail=f"Failed to parse form data: {str(form_error)}"
        )
    
    def _coerce_upload(value):
        """Extract UploadFile from form value."""
        if isinstance(value, UploadFile):
            return value
        if isinstance(value, (list, tuple)):
            for item in value:
                if isinstance(item, UploadFile):
                    return item
        return None
    
    upload = None
    # Try different field names in order of likelihood
    for key in ("file", "files", "cover", "cover_file", "file[]", "files[]"):
        if key not in form:
            continue
        candidate = _coerce_upload(form.get(key))
        if candidate is None and hasattr(form, "getlist"):
            candidate = _coerce_upload(form.getlist(key))
        if candidate is not None:
            upload = candidate
            logger.info(f"Found upload in '{key}' field: {candidate.filename}")
            break
    
    # Last resort: check all form items
    if upload is None and hasattr(form, "multi_items"):
        for key, value in form.multi_items():
            candidate = _coerce_upload(value)
            if candidate is not None:
                upload = candidate
                logger.info(f"Found upload in form field '{key}': {candidate.filename}")
                break
    
    if upload is None:
        form_keys = list(form.keys()) if hasattr(form, 'keys') else []
        logger.warning(f"No upload file found. Form keys: {form_keys}, User: {current_user.id}")
        raise HTTPException(
            status_code=400, 
            detail="No cover image provided. Please include a file in the 'file', 'files', 'cover', or 'cover_file' form field."
        )
    
    logger.info(f"Processing upload: filename={upload.filename}, content_type={upload.content_type}, user={current_user.id}")
    
    content_type = upload.content_type or "image/jpeg"
    if content_type not in ALLOWED_CONTENT_TYPES:
        logger.warning(f"Unsupported content type: {content_type}. Allowed: {list(ALLOWED_CONTENT_TYPES.keys())}")
        raise HTTPException(
            status_code=400, 
            detail={
                "error": f"Unsupported image type: {content_type}",
                "allowed_types": list(ALLOWED_CONTENT_TYPES.keys())
            }
        )
    
    # Read file data
    try:
        data = await upload.read()
        if not data:
            raise HTTPException(status_code=400, detail="Empty file upload")
        if len(data) > MAX_COVER_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Cover image exceeds {MAX_COVER_SIZE / (1024*1024):.0f} MB limit"
            )
    except HTTPException:
        raise
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"Failed to read uploaded file: {ex}")
    
    # Validate image signature (magic bytes)
    if len(data) < 16:
        logger.warning(f"File too small: {len(data)} bytes")
        raise HTTPException(status_code=400, detail="File too small to be a valid image")
    
    # Check for PNG, JPEG, or WebP signatures
    is_png = data.startswith(b"\x89PNG")
    is_jpeg = data.startswith(b"\xff\xd8")
    is_webp = data.startswith(b"RIFF") and b"WEBP" in data[:12]
    
    if not (is_png or is_jpeg or is_webp):
        logger.warning(f"Invalid image signature. First 16 bytes: {data[:16].hex()}")
        raise HTTPException(
            status_code=400, 
            detail={
                "error": "Invalid image file signature",
                "file_size": len(data),
                "first_bytes": data[:16].hex()
            }
        )
    
    # Derive extension from content type
    ext = ALLOWED_CONTENT_TYPES[content_type]
    
    # Generate unique R2 key for cover image
    # Format: covers/{user_id}/cover_{uuid}.{ext}
    r2_bucket = os.getenv("R2_BUCKET", "ppp-media").strip()
    if not r2_bucket:
        raise HTTPException(status_code=500, detail="R2_BUCKET environment variable not set")
    
    r2_key = f"covers/{current_user.id.hex}/cover_{uuid.uuid4().hex}{ext}"
    
    # Upload to R2
    try:
        from infrastructure import r2
        file_stream = BytesIO(data)
        r2_url = r2.upload_fileobj(
            r2_bucket,
            r2_key,
            file_stream,
            content_type=content_type
        )
        
        if not r2_url:
            raise HTTPException(status_code=500, detail="Failed to upload cover to R2 storage")
        
        logger.info(f"Cover image uploaded to R2: {r2_url} (user={current_user.id})")
        
        # Return R2 URL in all fields for backward compatibility
        return {
            "filename": r2_url,  # R2 URL
            "stored_as": r2_url,  # R2 URL
            "path": r2_url,  # R2 URL
            "content_type": content_type,
            "size": len(data),
        }
    except HTTPException:
        raise
    except Exception as ex:
        logger.error(f"Failed to upload cover to R2: {ex}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to upload cover to cloud storage: {ex}")
