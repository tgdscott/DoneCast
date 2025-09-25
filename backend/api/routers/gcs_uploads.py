import os
import re
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

try:
    from google.cloud import storage  # type: ignore
except Exception:  # pragma: no cover - optional at import, runtime will error if used without package
    storage = None  # type: ignore

router = APIRouter(prefix="/gcs", tags=["gcs"])


SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9._\- ]{1,200}$")
ALLOWED_CONTENT_TYPES = {
    "audio/mpeg",
    "audio/wav",
    "audio/x-wav",
    "audio/webm",
    "audio/ogg",
    "audio/mp4",
    "audio/aac",
    "audio/flac",
}


class SignedResumableRequest(BaseModel):
    filename: str
    contentType: str
    prefix: Optional[str] = None  # optional path prefix within bucket


class SignedResumableResponse(BaseModel):
    uploadUrl: str
    objectPath: str  # gs://bucket/key


def _validate_filename(name: str) -> str:
    # Disallow sneaky paths
    name = name.strip().replace("\\", "/")
    if "/" in name:
        name = name.split("/")[-1]
    if not SAFE_NAME_RE.match(name):
        raise HTTPException(status_code=400, detail="Invalid filename")
    return name


@router.post("/signed-resumable", response_model=SignedResumableResponse)
def create_signed_resumable(req: SignedResumableRequest):
    if storage is None:
        raise HTTPException(status_code=500, detail="google-cloud-storage not installed")

    bucket_name = os.getenv("GCS_UPLOAD_BUCKET")
    if not bucket_name:
        raise HTTPException(status_code=500, detail="GCS_UPLOAD_BUCKET not configured")

    content_type = req.contentType.strip().lower()
    if content_type not in ALLOWED_CONTENT_TYPES and not content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="Unsupported content type")

    filename = _validate_filename(req.filename)
    prefix = (req.prefix or "").strip().strip("/")
    if prefix:
        # Avoid any traversal in prefix; keep to safe characters and limited depth
        if not re.match(r"^[A-Za-z0-9/_\-]{1,200}$", prefix):
            raise HTTPException(status_code=400, detail="Invalid prefix")
        key = f"{prefix}/{filename}"
    else:
        key = filename

    client = storage.Client()  # uses ADC (e.g., Cloud Run service account)
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(key)

    # V4 signed URL for starting a resumable upload: requires special header
    headers = {"x-goog-resumable": "start"}
    url = blob.generate_signed_url(
        version="v4",
        expiration=timedelta(minutes=int(os.getenv("GCS_SIGNED_URL_TTL_MIN", "15"))),
        method="POST",
        content_type=content_type,
        headers=headers,
    )

    return SignedResumableResponse(
        uploadUrl=url,
        objectPath=f"gs://{bucket_name}/{key}",
    )
