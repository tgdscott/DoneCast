import logging
import os
import shutil
<<<<<<< HEAD
from datetime import datetime, timedelta, timezone
=======
from datetime import timedelta
>>>>>>> parent of d91e6271 (Merge branch 'main' into codex/fix-music-upload-issue-due-to-bucket-not-found-j04qa8)
from pathlib import Path
from typing import IO, Optional, Union

try:
    from google.cloud import storage
    from google.auth.exceptions import DefaultCredentialsError
    from google.api_core import exceptions as gcs_exceptions
except ImportError:
    storage = None
    DefaultCredentialsError = None
    gcs_exceptions = None

logger = logging.getLogger(__name__)

# --- GCS Client Initialization ---

_gcs_client = None
_gcs_credentials = None
_gcs_project = None
_signer_email = None

def _get_gcs_client():
    """Initializes and returns a GCS client, handling credentials gracefully."""
    global _gcs_client, _gcs_credentials, _gcs_project, _signer_email
    if _gcs_client:
        return _gcs_client

    if not storage:
        logger.debug("GCS client requested but google-cloud-storage not installed.")
        return None

    try:
        # In a GCP environment (Cloud Run, GCE), this will use the attached service account.
        # Locally, it will use `gcloud auth application-default login` credentials or GOOGLE_APPLICATION_CREDENTIALS.
        client = storage.Client()
        _gcs_client = client
        _gcs_credentials = getattr(client, "_credentials", None)
        _gcs_project = client.project
        # This is the crucial part: capture the service account email for signing.
        if hasattr(_gcs_credentials, "service_account_email"):
            _signer_email = _gcs_credentials.service_account_email
        logger.info(f"GCS client initialized for project {_gcs_project}. Signer: {_signer_email or 'N/A (will use key if available)'}")
        return _gcs_client
    except DefaultCredentialsError:
        logger.warning("GCS credentials not found. GCS operations will be disabled.") # type: ignore
        return None
    except Exception as e:
        logger.error("Failed to initialize GCS client: %s", e, exc_info=True)
        return None

# Initialize on first import
_get_gcs_client()

# --- Public API ---

def get_signed_url(bucket_name: str, key: str, expiration: int = 3600) -> Optional[str]:
    """Generates a signed URL for a GCS object, handling service account signing correctly."""
    client = _get_gcs_client()
    if not client:
        return None

    try:
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(key)
        # This is the fix: explicitly provide the service_account_email.
        # The library will then use the IAM API to sign the URL instead of looking for a private key.
        url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(seconds=expiration),
            method="GET",
            service_account_email=_signer_email,
        )
        return url
    except Exception as e:
        logger.error("Failed to sign URL for gs://%s/%s: %s", bucket_name, key, e, exc_info=True)
        # Re-raise the original error to be handled by the caller, which produces the 500 error you saw.
        raise

<<<<<<< HEAD
=======

def get_signed_url(bucket_name: str, key: str, expiration: int = 3600) -> Optional[str]:
    """Generates a signed URL for a GCS object, handling service account signing correctly."""

    expiration = max(1, int(expiration or 0))
    return _generate_signed_url(
        bucket_name,
        key,
        expires=timedelta(seconds=expiration),
        method="GET",
    )


def make_signed_url(
    bucket: str,
    key: str,
    minutes: int = 60,
    *,
    method: str = "GET",
    content_type: Optional[str] = None,
) -> str:
    """Return a signed URL or dev fallback for the given object."""

    minutes = max(1, int(minutes or 0))
    url: Optional[str] = None
    try:
        url = _generate_signed_url(
            bucket,
            key,
            expires=timedelta(minutes=minutes),
            method=method,
            content_type=content_type,
        )
    except Exception as exc:
        if not _should_fallback_to_local(exc):
            raise
        logger.warning(
            "GCS signed-url generation failed for gs://%s/%s in dev; using local media: %s",
            bucket,
            key,
            exc,
        )

    if url:
        return url

    fallback = _local_media_url(key)
    if fallback:
        if _is_dev_env():
            logger.debug(
                "DEV: Using local media fallback for gs://%s/%s -> %s",
                bucket,
                key,
                fallback,
            )
        return fallback

    raise RuntimeError(f"Unable to create signed URL for gs://{bucket}/{key}")
>>>>>>> parent of d91e6271 (Merge branch 'main' into codex/fix-music-upload-issue-due-to-bucket-not-found-j04qa8)


def _is_dev_env() -> bool:
    val = (os.getenv("APP_ENV") or os.getenv("ENV") or os.getenv("PYTHON_ENV") or "dev").strip().lower()
    return val in {"dev", "development", "local", "test", "testing"}


def _write_local_bytes(bucket_name: str, key: str, data: bytes) -> str:
<<<<<<< HEAD
    local_path = Path(os.getenv("MEDIA_DIR", "media")) / key
=======
    rel_key = _normalize_object_key(key)
    local_root = _resolve_local_media_dir()
    local_path = local_root / rel_key
>>>>>>> parent of d91e6271 (Merge branch 'main' into codex/fix-music-upload-issue-due-to-bucket-not-found-j04qa8)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_bytes(data)
    logger.info("DEV: Wrote GCS upload for gs://%s/%s to %s", bucket_name, key, local_path)
    return rel_key.as_posix()


def _write_local_stream(bucket_name: str, key: str, fileobj: IO) -> str:
    rel_key = _normalize_object_key(key)
    local_root = _resolve_local_media_dir()
    local_path = local_root / rel_key
    local_path.parent.mkdir(parents=True, exist_ok=True)
    with open(local_path, "wb") as f:
        try:
            if hasattr(fileobj, "seek"):
                fileobj.seek(0)
        except Exception:
            pass
        shutil.copyfileobj(fileobj, f)
    try:
        if hasattr(fileobj, "seek"):
            fileobj.seek(0)
    except Exception:
        pass
<<<<<<< HEAD
    logger.info(f"DEV: Wrote GCS upload for gs://{bucket_name}/{key} to {local_path}")
    return str(local_path)
=======
    logger.info("DEV: Wrote GCS upload for gs://%s/%s to %s", bucket_name, key, local_path)
    return rel_key.as_posix()
>>>>>>> parent of d91e6271 (Merge branch 'main' into codex/fix-music-upload-issue-due-to-bucket-not-found-j04qa8)


def _should_fallback_to_local(exc: Exception) -> bool:
    if not _is_dev_env():
        return False
    if gcs_exceptions and isinstance(exc, gcs_exceptions.NotFound):
        return True
    message = str(exc).lower()
    return "bucket does not exist" in message or "notfound" in message


def upload_fileobj(bucket_name: str, key: str, fileobj: IO, content_type: Optional[str] = None, **kwargs) -> str:
    """Uploads a file-like object to GCS. Returns gs:// URI."""
    client = _get_gcs_client()
    if not client:
        return _write_local_stream(bucket_name, key, fileobj)

    bucket = client.bucket(bucket_name)
    blob = bucket.blob(key)
    try:
        blob.upload_from_file(fileobj, content_type=content_type)
        logger.info(f"Uploaded to gs://{bucket_name}/{key}")
        return f"gs://{bucket_name}/{key}"
    except Exception as exc:
        if _should_fallback_to_local(exc):
            logger.warning(
                "GCS upload failed for gs://%s/%s in dev environment; falling back to local storage: %s",
                bucket_name,
                key,
                exc,
            )
            return _write_local_stream(bucket_name, key, fileobj)
        raise


def upload_bytes(bucket_name: str, key: str, data: bytes, content_type: Optional[str] = None) -> str:
    """Uploads bytes to GCS. Returns gs:// URI."""
    client = _get_gcs_client()
    if not client:
        return _write_local_bytes(bucket_name, key, data)

    bucket = client.bucket(bucket_name)
    blob = bucket.blob(key)
    try:
        blob.upload_from_string(data, content_type=content_type)
        logger.info(f"Uploaded to gs://{bucket_name}/{key}")
        return f"gs://{bucket_name}/{key}"
    except Exception as exc:
        if _should_fallback_to_local(exc):
            logger.warning(
                "GCS upload failed for gs://%s/%s in dev environment; falling back to local storage: %s",
                bucket_name,
                key,
                exc,
            )
            return _write_local_bytes(bucket_name, key, data)
        raise


def download_gcs_bytes(bucket_name: str, key: str) -> Optional[bytes]:
    """Downloads an object from GCS as bytes."""
    client = _get_gcs_client()
    if not client:
        # Dev/local fallback: read from local media directory
        local_path = Path(os.getenv("MEDIA_DIR", "media")) / key
        if local_path.exists():
            logger.info(f"DEV: Reading GCS download for gs://{bucket_name}/{key} from {local_path}")
            return local_path.read_bytes()
        return None

    try:
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(key)
        return blob.download_as_bytes()
    except Exception as e:
        logger.error("Failed to download gs://%s/%s: %s", bucket_name, key, e)
        return None


def delete_gcs_blob(bucket_name: str, blob_name: str) -> None:
    """Deletes a blob from a GCS bucket."""
    client = _get_gcs_client()
    if not client:
        logger.warning("GCS client not available, cannot delete gs://%s/%s", bucket_name, blob_name)
        return

    try:
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.delete()
        logger.info("Deleted gs://%s/%s", bucket_name, blob_name)
    except Exception as e:
        logger.error("Failed to delete gs://%s/%s: %s", bucket_name, blob_name, e)
        # Do not re-raise, as the caller often wants to continue on failure
