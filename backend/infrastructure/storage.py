"""Storage backend abstraction layer.

Routes storage operations to either GCS or R2 based on STORAGE_BACKEND env var.
This allows gradual migration from GCS to R2 without changing application code.

Environment Variables:
    STORAGE_BACKEND: "gcs" or "r2" (default: "gcs")
    GCS_BUCKET: Google Cloud Storage bucket name
    R2_BUCKET: Cloudflare R2 bucket name
"""

from __future__ import annotations

import logging
import os
from typing import IO, Optional

# Import both storage backends
from infrastructure import gcs, r2


logger = logging.getLogger(__name__)


def _get_backend() -> str:
    """Get configured storage backend (gcs or r2)."""
    backend = os.getenv("STORAGE_BACKEND", "gcs").lower()
    if backend not in ("gcs", "r2"):
        logger.warning(f"Invalid STORAGE_BACKEND '{backend}', defaulting to 'gcs'")
        return "gcs"
    return backend


def _get_bucket_name() -> str:
    """Get bucket name for active storage backend."""
    backend = _get_backend()
    if backend == "r2":
        return os.getenv("R2_BUCKET", "ppp-media").strip()
    else:
        return os.getenv("GCS_BUCKET", "ppp-media-us-west1").strip()


def upload_fileobj(
    bucket_name: str,
    key: str,
    fileobj: IO,
    content_type: str = "application/octet-stream",
    allow_fallback: bool = False,  # Default to False - require cloud storage
) -> Optional[str]:
    """Upload file-like object to configured storage backend.
    
    Args:
        bucket_name: Bucket name (ignored, uses configured bucket)
        key: Object key/path
        fileobj: File-like object to upload
        content_type: MIME type
        allow_fallback: If False, raise exception instead of falling back to local storage.
                       Set to False for production-critical uploads that MUST be in cloud storage.
    
    Returns:
        Public URL (gs://... or https://...) if successful, None if failed
        Raises RuntimeError if upload fails and allow_fallback=False
    
    Raises:
        RuntimeError: If upload fails and allow_fallback=False
    """
    backend = _get_backend()
    bucket = _get_bucket_name()
    
    if backend == "r2":
        logger.info(f"[storage] Uploading {key} to R2 bucket {bucket}")
        result = r2.upload_fileobj(bucket, key, fileobj, content_type)
        if result:
            logger.info(f"[storage] Successfully uploaded to R2: {result}")
        else:
            logger.error(f"[storage] R2 upload failed for {key}")
            if not allow_fallback:
                raise RuntimeError(f"R2 upload failed for {key} and fallback is disabled")
        return result
    else:
        logger.info(f"[storage] Uploading {key} to GCS bucket {bucket} (allow_fallback={allow_fallback})")
        try:
            result = gcs.upload_fileobj(bucket, key, fileobj, content_type, allow_fallback=allow_fallback)
            if result and (result.startswith("gs://") or result.startswith("http")):
                logger.info(f"[storage] Successfully uploaded to GCS: {result}")
            elif result:
                # Local fallback path was returned
                logger.warning(f"[storage] Upload fell back to local storage: {result}")
                if not allow_fallback:
                    raise RuntimeError(f"GCS upload failed for {key} and fallback is disabled (returned: {result})")
            else:
                logger.error(f"[storage] GCS upload returned None for {key}")
                if not allow_fallback:
                    raise RuntimeError(f"GCS upload failed for {key} and fallback is disabled (returned None)")
            return result
        except RuntimeError:
            # Re-raise RuntimeError as-is (it's from gcs.upload_fileobj when allow_fallback=False)
            raise
        except Exception as e:
            logger.error(f"[storage] Unexpected error during GCS upload: {e}", exc_info=True)
            if not allow_fallback:
                raise RuntimeError(f"GCS upload failed for {key}: {e}") from e
            return None


def upload_bytes(
    bucket_name: str,
    key: str,
    data: bytes,
    content_type: str = "application/octet-stream",
    allow_fallback: bool = False,  # Default to False - require cloud storage
) -> Optional[str]:
    """Upload bytes to configured storage backend.
    
    Args:
        bucket_name: Bucket name (ignored, uses configured bucket)
        key: Object key/path
        data: Bytes to upload
        content_type: MIME type
        allow_fallback: If False, raise exception instead of falling back to local storage.
                       Set to False for production-critical uploads that MUST be in cloud storage.
    
    Returns:
        Public URL (gs://... or https://...) if successful, None if failed
        Raises RuntimeError if upload fails and allow_fallback=False
    
    Raises:
        RuntimeError: If upload fails and allow_fallback=False
    """
    backend = _get_backend()
    bucket = _get_bucket_name()
    
    if backend == "r2":
        logger.info(f"[storage] Uploading {len(data)} bytes to R2 bucket {bucket}")
        result = r2.upload_bytes(bucket, key, data, content_type)
        if result:
            logger.info(f"[storage] Successfully uploaded to R2: {result}")
        else:
            logger.error(f"[storage] R2 upload failed for {key}")
            if not allow_fallback:
                raise RuntimeError(f"R2 upload failed for {key} and fallback is disabled")
        return result
    else:
        logger.info(f"[storage] Uploading {len(data)} bytes to GCS bucket {bucket} (allow_fallback={allow_fallback})")
        try:
            result = gcs.upload_bytes(bucket, key, data, content_type, allow_fallback=allow_fallback)
            if result and (result.startswith("gs://") or result.startswith("http")):
                logger.info(f"[storage] Successfully uploaded to GCS: {result}")
            elif result:
                # Local fallback path was returned
                logger.warning(f"[storage] Upload fell back to local storage: {result}")
                if not allow_fallback:
                    raise RuntimeError(f"GCS upload failed for {key} and fallback is disabled (returned: {result})")
            else:
                logger.error(f"[storage] GCS upload returned None for {key}")
                if not allow_fallback:
                    raise RuntimeError(f"GCS upload failed for {key} and fallback is disabled (returned None)")
            return result
        except RuntimeError:
            # Re-raise RuntimeError as-is (it's from gcs.upload_bytes when allow_fallback=False)
            raise
        except Exception as e:
            logger.error(f"[storage] Unexpected error during GCS upload: {e}", exc_info=True)
            if not allow_fallback:
                raise RuntimeError(f"GCS upload failed for {key}: {e}") from e
            return None


def download_bytes(bucket_name: str, key: str) -> Optional[bytes]:
    """Download object as bytes from configured storage backend.
    
    Tries R2 first if configured, falls back to GCS for backward compatibility.
    
    Args:
        bucket_name: Bucket name (ignored, uses configured bucket)
        key: Object key/path
    
    Returns:
        File contents as bytes, or None if not found
    """
    backend = _get_backend()
    bucket = _get_bucket_name()
    
    # Try active backend first
    if backend == "r2":
        logger.debug(f"[storage] Downloading {key} from R2 bucket {bucket}")
        data = r2.download_bytes(bucket, key)
        if data is not None:
            return data
        
        # Fall back to GCS for migration period
        logger.debug(f"[storage] Not found in R2, trying GCS fallback")
        gcs_bucket = os.getenv("GCS_BUCKET", "ppp-media-us-west1")
        return gcs.download_bytes(gcs_bucket, key)
    else:
        logger.debug(f"[storage] Downloading {key} from GCS bucket {bucket}")
        return gcs.download_bytes(bucket, key)


def blob_exists(bucket_name: str, key: str) -> bool:
    """Check if object exists in configured storage backend.
    
    Args:
        bucket_name: Bucket name (ignored, uses configured bucket)
        key: Object key/path
    
    Returns:
        True if object exists, False otherwise
    """
    backend = _get_backend()
    bucket = _get_bucket_name()
    
    if backend == "r2":
        exists = r2.blob_exists(bucket, key)
        if exists:
            return True
        
        # Check GCS fallback during migration
        gcs_bucket = os.getenv("GCS_BUCKET", "ppp-media-us-west1")
        return gcs.blob_exists(gcs_bucket, key) or False
    else:
        result = gcs.blob_exists(bucket, key)
        return result if result is not None else False


def delete_blob(bucket_name: str, key: str) -> bool:
    """Delete object from configured storage backend.
    
    Args:
        bucket_name: Bucket name (ignored, uses configured bucket)
        key: Object key/path
    
    Returns:
        True if deleted successfully, False otherwise
    """
    backend = _get_backend()
    bucket = _get_bucket_name()
    
    if backend == "r2":
        logger.debug(f"[storage] Deleting {key} from R2 bucket {bucket}")
        return r2.delete_blob(bucket, key)
    else:
        logger.debug(f"[storage] Deleting {key} from GCS bucket {bucket}")
        try:
            gcs.delete_gcs_blob(bucket, key)
            return True
        except Exception as e:
            logger.error(f"[storage] Failed to delete {key} from GCS: {e}")
            return False


def generate_signed_url(
    bucket_name: str,
    key: str,
    expiration: int = 3600,
    method: str = "GET",
) -> Optional[str]:
    """Generate presigned URL for object.
    
    Args:
        bucket_name: Bucket name (ignored, uses configured bucket)
        key: Object key/path
        expiration: URL expiration in seconds
        method: HTTP method (GET, PUT, POST, DELETE)
    
    Returns:
        Presigned URL string, or None if failed
    """
    backend = _get_backend()
    bucket = _get_bucket_name()
    
    if backend == "r2":
        logger.debug(f"[storage] Generating R2 signed URL for {key}")
        return r2.generate_signed_url(bucket, key, expiration, method)
    else:
        logger.debug(f"[storage] Generating GCS signed URL for {key}")
        return gcs.make_signed_url(bucket, key, expiration=expiration, method=method)


def get_public_audio_url(
    path: Optional[str],
    expiration_days: int = 7,
    **kwargs,
) -> Optional[str]:
    """Generate signed URL for audio playback.
    
    Detects storage backend from path format:
    - Starts with "r2://" or contains R2 bucket name or ".r2.cloudflarestorage.com" → use R2
    - Starts with "gs://" or contains GCS bucket name → use GCS
    
    Args:
        path: Storage path (e.g., "gs://bucket/file.mp3", "r2://bucket/file.mp3", 
              or "https://bucket.account.r2.cloudflarestorage.com/key")
        expiration_days: Number of days until URL expires
    
    Returns:
        Signed URL string, or None if path is invalid
    """
    if not path:
        return None
    
    # Auto-detect backend from path
    # Check for R2 indicators: r2:// prefix, R2 bucket name, or R2 domain
    r2_bucket = os.getenv("R2_BUCKET", "").strip()
    is_r2 = (
        path.startswith("r2://") 
        or (r2_bucket and r2_bucket in path)
        or ".r2.cloudflarestorage.com" in path.lower()
    )
    
    if is_r2:
        logger.debug(f"[storage] Generating R2 audio URL for {path}")
        return r2.get_public_audio_url(path, expiration_days, **kwargs)
    else:
        logger.debug(f"[storage] Generating GCS audio URL for {path}")
        return gcs.get_public_audio_url(path, expiration_days, **kwargs)


# Backward compatibility aliases
get_signed_url = generate_signed_url
delete_gcs_blob = delete_blob
make_signed_url = generate_signed_url
upload_file = upload_fileobj
