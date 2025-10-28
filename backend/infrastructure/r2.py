"""Cloudflare R2 storage client using S3-compatible API.

This module provides R2 object storage operations with the same interface
as the GCS module, allowing drop-in replacement for media file storage.

R2 benefits over GCS:
- Zero egress fees (vs $0.12/GB for GCS)
- Built-in global CDN (Cloudflare's edge network)
- S3-compatible API (industry standard)
- Lower storage costs ($0.015/GB vs $0.020/GB)
"""

from __future__ import annotations

import logging
import os
from datetime import timedelta
from pathlib import Path
from typing import IO, Optional
from urllib.parse import quote

try:
    import boto3
    from botocore.client import Config
    from botocore.exceptions import ClientError, NoCredentialsError
except ImportError:
    boto3 = None  # type: ignore[assignment]
    Config = None  # type: ignore[assignment]
    ClientError = None  # type: ignore[assignment]
    NoCredentialsError = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)

# Cached R2 client
_R2_CLIENT = None


def _get_r2_client():
    """Get or create cached boto3 S3 client configured for Cloudflare R2."""
    global _R2_CLIENT
    
    if _R2_CLIENT is not None:
        return _R2_CLIENT
    
    if boto3 is None:
        logger.error("boto3 not installed - R2 operations will fail")
        return None
    
    # Get R2 credentials from environment
    account_id = os.getenv("R2_ACCOUNT_ID")
    access_key_id = os.getenv("R2_ACCESS_KEY_ID")
    secret_access_key = os.getenv("R2_SECRET_ACCESS_KEY")
    
    if not all([account_id, access_key_id, secret_access_key]):
        logger.warning(
            "Missing R2 credentials (R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY). "
            "R2 operations will fail."
        )
        return None
    
    # R2 endpoint format: https://<account_id>.r2.cloudflarestorage.com
    endpoint_url = f"https://{account_id}.r2.cloudflarestorage.com"
    
    try:
        client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
            ),
            region_name="auto",  # R2 uses "auto" for automatic region selection
        )
        
        _R2_CLIENT = client
        logger.info(f"R2 client initialized for account {account_id}")
        return client
        
    except Exception as e:
        logger.error(f"Failed to initialize R2 client: {e}")
        return None


def upload_fileobj(
    bucket_name: str,
    key: str,
    fileobj: IO,
    content_type: str = "application/octet-stream",
) -> Optional[str]:
    """Upload a file-like object to R2.
    
    Args:
        bucket_name: R2 bucket name (e.g., "ppp-media")
        key: Object key/path (e.g., "audio/episode123.mp3")
        fileobj: File-like object to upload
        content_type: MIME type (e.g., "audio/mpeg")
    
    Returns:
        Public R2 URL if successful, None if failed
    """
    client = _get_r2_client()
    if client is None:
        logger.error(f"Cannot upload to R2 - client not initialized")
        return None
    
    try:
        # Reset file pointer to beginning
        fileobj.seek(0)
        
        # Upload to R2
        client.upload_fileobj(
            fileobj,
            bucket_name,
            key,
            ExtraArgs={"ContentType": content_type},
        )
        
        # Return public R2 URL
        # Format: https://ppp-media.{account_id}.r2.cloudflarestorage.com/path/to/file.mp3
        account_id = os.getenv("R2_ACCOUNT_ID")
        url = f"https://{bucket_name}.{account_id}.r2.cloudflarestorage.com/{key}"
        
        logger.info(f"[R2] Uploaded {key} to bucket {bucket_name}")
        return url
        
    except ClientError as e:
        logger.error(f"[R2] Failed to upload {key}: {e}")
        return None
    except Exception as e:
        logger.error(f"[R2] Unexpected error uploading {key}: {e}")
        return None


def upload_bytes(
    bucket_name: str,
    key: str,
    data: bytes,
    content_type: str = "application/octet-stream",
) -> Optional[str]:
    """Upload bytes to R2.
    
    Args:
        bucket_name: R2 bucket name
        key: Object key/path
        data: Bytes to upload
        content_type: MIME type
    
    Returns:
        Public R2 URL if successful, None if failed
    """
    client = _get_r2_client()
    if client is None:
        logger.error(f"Cannot upload to R2 - client not initialized")
        return None
    
    try:
        # Upload to R2
        client.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        
        # Return public R2 URL
        account_id = os.getenv("R2_ACCOUNT_ID")
        url = f"https://{bucket_name}.{account_id}.r2.cloudflarestorage.com/{key}"
        
        logger.info(f"[R2] Uploaded {len(data)} bytes to {key}")
        return url
        
    except ClientError as e:
        logger.error(f"[R2] Failed to upload {key}: {e}")
        return None
    except Exception as e:
        logger.error(f"[R2] Unexpected error uploading {key}: {e}")
        return None


def download_bytes(bucket_name: str, key: str) -> Optional[bytes]:
    """Download object from R2 as bytes.
    
    Args:
        bucket_name: R2 bucket name
        key: Object key/path
    
    Returns:
        File contents as bytes, or None if failed
    """
    client = _get_r2_client()
    if client is None:
        logger.error(f"Cannot download from R2 - client not initialized")
        return None
    
    try:
        response = client.get_object(Bucket=bucket_name, Key=key)
        data = response["Body"].read()
        logger.info(f"[R2] Downloaded {len(data)} bytes from {key}")
        return data
        
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchKey":
            logger.warning(f"[R2] Object not found: {key}")
        else:
            logger.error(f"[R2] Failed to download {key}: {e}")
        return None
    except Exception as e:
        logger.error(f"[R2] Unexpected error downloading {key}: {e}")
        return None


def blob_exists(bucket_name: str, key: str) -> bool:
    """Check if object exists in R2.
    
    Args:
        bucket_name: R2 bucket name
        key: Object key/path
    
    Returns:
        True if object exists, False otherwise
    """
    client = _get_r2_client()
    if client is None:
        return False
    
    try:
        client.head_object(Bucket=bucket_name, Key=key)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "404":
            return False
        logger.error(f"[R2] Error checking if {key} exists: {e}")
        return False
    except Exception as e:
        logger.error(f"[R2] Unexpected error checking {key}: {e}")
        return False


def delete_blob(bucket_name: str, key: str) -> bool:
    """Delete object from R2.
    
    Args:
        bucket_name: R2 bucket name
        key: Object key/path
    
    Returns:
        True if deleted successfully, False otherwise
    """
    client = _get_r2_client()
    if client is None:
        logger.error(f"Cannot delete from R2 - client not initialized")
        return False
    
    try:
        client.delete_object(Bucket=bucket_name, Key=key)
        logger.info(f"[R2] Deleted {key} from bucket {bucket_name}")
        return True
        
    except ClientError as e:
        logger.error(f"[R2] Failed to delete {key}: {e}")
        return False
    except Exception as e:
        logger.error(f"[R2] Unexpected error deleting {key}: {e}")
        return False


def generate_signed_url(
    bucket_name: str,
    key: str,
    expiration: int = 3600,
    method: str = "GET",
) -> Optional[str]:
    """Generate presigned URL for R2 object.
    
    Args:
        bucket_name: R2 bucket name
        key: Object key/path
        expiration: URL expiration in seconds (default 1 hour)
        method: HTTP method (GET, PUT, POST, DELETE)
    
    Returns:
        Presigned URL string, or None if failed
    """
    client = _get_r2_client()
    if client is None:
        logger.error(f"Cannot generate signed URL - R2 client not initialized")
        return None
    
    try:
        # Map HTTP methods to boto3 operations
        operation_map = {
            "GET": "get_object",
            "PUT": "put_object",
            "POST": "put_object",  # R2 doesn't have separate POST operation
            "DELETE": "delete_object",
        }
        
        operation = operation_map.get(method.upper(), "get_object")
        
        url = client.generate_presigned_url(
            ClientMethod=operation,
            Params={"Bucket": bucket_name, "Key": key},
            ExpiresIn=expiration,
        )
        
        logger.debug(f"[R2] Generated {method} signed URL for {key} (expires in {expiration}s)")
        return url
        
    except ClientError as e:
        logger.error(f"[R2] Failed to generate signed URL for {key}: {e}")
        return None
    except Exception as e:
        logger.error(f"[R2] Unexpected error generating signed URL for {key}: {e}")
        return None


def get_public_url(bucket_name: str, key: str) -> str:
    """Get public R2 URL (for objects in public buckets).
    
    For podcast RSS feeds, use generate_signed_url() instead for security.
    This is useful for publicly accessible assets.
    
    Args:
        bucket_name: R2 bucket name
        key: Object key/path
    
    Returns:
        Public R2 URL
    """
    account_id = os.getenv("R2_ACCOUNT_ID", "UNKNOWN")
    # URL-encode the key to handle special characters
    encoded_key = quote(key, safe="/")
    return f"https://{bucket_name}.{account_id}.r2.cloudflarestorage.com/{encoded_key}"


def get_public_audio_url(
    r2_path: Optional[str],
    expiration_days: int = 7,
) -> Optional[str]:
    """Generate signed URL for audio playback from R2 path.
    
    This mirrors the GCS get_public_audio_url() function for drop-in replacement.
    
    Args:
        r2_path: R2 path in format "bucket/path/to/file.mp3" or None
        expiration_days: Number of days until URL expires (default 7)
    
    Returns:
        Signed URL string, or None if path is invalid
    """
    if not r2_path:
        return None
    
    # Parse bucket and key from path
    # Format: "ppp-media/audio/episode123.mp3" or "https://..."
    if r2_path.startswith("http"):
        # Already a URL, return as-is (for backward compatibility)
        return r2_path
    
    # Remove r2:// prefix if present
    if r2_path.startswith("r2://"):
        r2_path = r2_path[5:]
    
    # Split bucket and key
    parts = r2_path.split("/", 1)
    if len(parts) != 2:
        logger.warning(f"Invalid R2 path format: {r2_path}")
        return None
    
    bucket_name, key = parts
    
    # Generate signed URL with expiration
    expiration_seconds = expiration_days * 24 * 60 * 60
    return generate_signed_url(bucket_name, key, expiration=expiration_seconds)


# Backward compatibility aliases (match GCS module API)
get_signed_url = generate_signed_url
delete_gcs_blob = delete_blob  # For code that still uses "gcs" naming
upload_file = upload_fileobj  # Alias for consistency
