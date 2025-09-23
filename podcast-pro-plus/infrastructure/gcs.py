import os, datetime
from typing import BinaryIO, Optional
from google.cloud import storage

_client = storage.Client()

def upload_bytes(bucket: str, key: str, data: bytes, content_type: str) -> str:
    """Upload an in-memory bytes payload to GCS.

    Note: For large files, prefer upload_fileobj() to avoid duplicating data in memory.
    """
    b = _client.bucket(bucket)
    blob = b.blob(key)
    blob.upload_from_string(data, content_type=content_type)
    return f"gs://{bucket}/{key}"

def upload_fileobj(bucket: str, key: str, fileobj: BinaryIO, *, size: Optional[int] = None, content_type: str = "application/octet-stream", chunk_mb: int = 8) -> str:
    """Upload from a file-like object to GCS using a resumable upload.

    - Does not buffer the whole content in memory
    - Allows setting a larger chunk size for better throughput
    - If size is provided, passes it to the client for efficiency
    """
    b = _client.bucket(bucket)
    blob = b.blob(key)
    # Use a larger chunk size to improve throughput on large uploads
    # Must be a multiple of 256KB; 8MB is a good default.
    try:
        blob.chunk_size = max(256 * 1024, int(chunk_mb) * 1024 * 1024)
    except Exception:
        blob.chunk_size = 8 * 1024 * 1024
    # Ensure file pointer is at start
    try:
        fileobj.seek(0)
    except Exception:
        pass
    if size is not None and size >= 0:
        blob.upload_from_file(fileobj, size=size, content_type=content_type)
    else:
        blob.upload_from_file(fileobj, content_type=content_type)
    return f"gs://{bucket}/{key}"

def make_signed_url(bucket: str, key: str, minutes: int = 60) -> str:
    b = _client.bucket(bucket)
    blob = b.blob(key)
    return blob.generate_signed_url(
        version="v4",
        expiration=datetime.timedelta(minutes=minutes),
        method="GET",
    )
