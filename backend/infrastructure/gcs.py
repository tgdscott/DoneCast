import os, datetime, pathlib
from typing import BinaryIO, Optional
from google.cloud import storage

# --- Local Dev Sandbox Implementation ---
def _is_dev_env() -> bool:
    val = (os.getenv("APP_ENV") or os.getenv("ENV") or os.getenv("PYTHON_ENV") or "dev").strip().lower()
    return val in {"dev", "development", "local", "test", "testing"}

IS_DEV_ENV = _is_dev_env()

# In dev mode, we don't need a real client.
_client: Optional[storage.Client] = None
if not IS_DEV_ENV:
    try:
        _client = storage.Client()
    except Exception as e:
        # This will allow the app to start, but GCS calls will fail.
        # Good for local dev without gcloud auth.
        print(f"Warning: Failed to initialize Google Cloud Storage client: {e}")

def _local_upload(key: str, data_or_fileobj: bytes | BinaryIO) -> str:
    """Helper to write data to the local MEDIA_DIR and return the filename."""
    from api.core.paths import MEDIA_DIR
    # The 'key' from GCS corresponds to the object path inside the bucket.
    # We'll save it directly under MEDIA_DIR, using just the basename.
    dest_path = MEDIA_DIR / os.path.basename(key)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    if isinstance(data_or_fileobj, bytes):
        dest_path.write_bytes(data_or_fileobj)
    else: # BinaryIO
        try:
            data_or_fileobj.seek(0)
        except Exception:
            pass
        with open(dest_path, "wb") as f:
            # For local dev, reading the whole thing is fine and simple.
            f.write(data_or_fileobj.read())

    # Return the simple filename. The `upload_media_files` function will store this
    # in the DB. The app serves `/static/media` from MEDIA_DIR, so this works.
    return dest_path.name


def upload_bytes(bucket: str, key: str, data: bytes, content_type: str) -> str:
    """Upload an in-memory bytes payload to GCS.

    Note: For large files, prefer upload_fileobj() to avoid duplicating data in memory.
    """
    if IS_DEV_ENV:
        return _local_upload(key, data)

    if not _client:
        raise RuntimeError("GCS client not initialized. Is APP_ENV set correctly and are you authenticated?")

    b = _client.bucket(bucket)
    blob = b.blob(key)
    blob.upload_from_string(data, content_type=content_type)
    return f"gs://{bucket}/{key}"

def upload_fileobj(bucket: str, key: str, fileobj: BinaryIO, *, size: Optional[int] = None, content_type: str = "application/octet-stream", chunk_mb: int | None = None) -> str:
    """Upload from a file-like object to GCS using a resumable upload.

    - Does not buffer the whole content in memory
    - Allows setting a larger chunk size for better throughput
    - If size is provided, passes it to the client for efficiency
    """
    if IS_DEV_ENV:
        return _local_upload(key, fileobj)

    if not _client:
        raise RuntimeError("GCS client not initialized. Is APP_ENV set correctly and are you authenticated?")

    b = _client.bucket(bucket)
    blob = b.blob(key)
    # Use a larger chunk size to improve throughput on large uploads
    # Must be a multiple of 256KB. Default to env GCS_CHUNK_MB or 32MB.
    if chunk_mb is None:
        try:
            chunk_mb = int(os.getenv("GCS_CHUNK_MB", "32"))
        except Exception:
            chunk_mb = 32
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
    if IS_DEV_ENV:
        # In local dev, assets are served from MEDIA_DIR via /static/media
        name = os.path.basename(key)
        return f"/static/media/{name}"

    if not _client:
        raise RuntimeError("GCS client not initialized.")

    b = _client.bucket(bucket)
    blob = b.blob(key)
    return blob.generate_signed_url(
        version="v4",
        expiration=datetime.timedelta(minutes=minutes),
        method="GET",
    )

def delete_blob(bucket: str, key: str):
    """Deletes a blob from GCS or the local filesystem for dev."""
    if IS_DEV_ENV:
        # The local implementation uses the key as the filename
        from api.core.paths import MEDIA_DIR
        try:
            (MEDIA_DIR / os.path.basename(key)).unlink(missing_ok=True)
        except Exception as e:
            print(f"Warning: local file delete failed for {key}: {e}")
        return

    if not _client:
        raise RuntimeError("GCS client not initialized.")

    try:
        b = _client.bucket(bucket)
        blob = b.blob(key)
        blob.delete()
    except Exception as e:
        # Log and ignore, as per the pattern in delete_media_item
        print(f"Warning: Failed to delete GCS blob gs://{bucket}/{key}: {e}")

def download_bytes(bucket: str, key: str) -> bytes:
    """Download an object and return contents as bytes (dev/prod aware)."""
    if IS_DEV_ENV:
        # Read from local MEDIA_DIR mirror in dev
        from api.core.paths import MEDIA_DIR  # type: ignore
        path = (MEDIA_DIR / os.path.basename(key)).resolve()
        with open(path, "rb") as f:
            return f.read()
    if not _client:
        raise RuntimeError("GCS client not initialized.")
    b = _client.bucket(bucket)
    blob = b.blob(key)
    return blob.download_as_bytes()
