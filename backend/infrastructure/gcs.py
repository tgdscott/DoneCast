import logging
import os
import shutil
from datetime import timedelta
from pathlib import Path
from typing import IO, Optional

try:
    from google.cloud import storage
    from google.auth.exceptions import DefaultCredentialsError
    from google.api_core import exceptions as gcs_exceptions
except ImportError:
    storage = None
    DefaultCredentialsError = None
    gcs_exceptions = None

logger = logging.getLogger(__name__)


_LOCAL_MEDIA_DIR: Optional[Path] = None


def _resolve_local_media_dir() -> Path:
    """Return the directory that should hold local media fallbacks."""

    global _LOCAL_MEDIA_DIR
    if _LOCAL_MEDIA_DIR is not None:
        return _LOCAL_MEDIA_DIR

    candidates: list[Path] = []

    env_override = (os.getenv("MEDIA_ROOT") or os.getenv("MEDIA_DIR") or "").strip()
    if env_override:
        candidates.append(Path(env_override).expanduser())

    try:
        # Prefer the canonical path used by the API layer when available.
        from api.core.paths import MEDIA_DIR as API_MEDIA_DIR  # type: ignore

        if isinstance(API_MEDIA_DIR, Path):
            candidates.append(API_MEDIA_DIR)
        elif API_MEDIA_DIR:
            candidates.append(Path(API_MEDIA_DIR))
    except Exception:
        pass

    # Final fallback lives inside the repository for local dev runs.
    candidates.append(Path("local_media"))

    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except Exception:
            resolved = candidate
        try:
            resolved.mkdir(parents=True, exist_ok=True)
        except Exception:
            continue
        _LOCAL_MEDIA_DIR = resolved
        return resolved

    # In the unlikely event all candidates failed, fall back to cwd/media.
    fallback = Path("media")
    fallback.mkdir(parents=True, exist_ok=True)
    _LOCAL_MEDIA_DIR = fallback
    return fallback


def _normalize_object_key(key: str) -> Path:
    """Normalize an object key to a safe relative Path."""

    key = (key or "").replace("\\", "/").strip("/")
    parts = [part for part in key.split("/") if part and part not in {".", ".."}]
    return Path(*parts)


def _local_media_url(key: str) -> Optional[str]:
    rel_key = _normalize_object_key(key)
    if not rel_key.parts:
        return None

    local_root = _resolve_local_media_dir()
    candidate = local_root / rel_key
    if not candidate.exists():
        return None
    return f"/static/media/{rel_key.as_posix()}"

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

def _generate_signed_url(
    bucket_name: str,
    key: str,
    *,
    expires: timedelta,
    method: str = "GET",
    content_type: Optional[str] = None,
) -> Optional[str]:
    client = _get_gcs_client()
    if not client:
        return None

    try:
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(key)
        kwargs = {
            "version": "v4",
            "expiration": expires,
            "method": method,
            "service_account_email": _signer_email,
        }
        if content_type and method.upper() in {"POST", "PUT"}:
            kwargs["content_type"] = content_type
        return blob.generate_signed_url(**kwargs)
    except Exception as exc:
        logger.error(
            "Failed to sign URL for gs://%s/%s: %s",
            bucket_name,
            key,
            exc,
            exc_info=True,
        )
        raise


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


def _is_dev_env() -> bool:
    val = (os.getenv("APP_ENV") or os.getenv("ENV") or os.getenv("PYTHON_ENV") or "dev").strip().lower()
    return val in {"dev", "development", "local", "test", "testing"}


def _write_local_bytes(bucket_name: str, key: str, data: bytes) -> str:
    rel_key = _normalize_object_key(key)
    local_root = _resolve_local_media_dir()
    local_path = local_root / rel_key
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
    logger.info("DEV: Wrote GCS upload for gs://%s/%s to %s", bucket_name, key, local_path)
    return rel_key.as_posix()


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
        rel_key = _normalize_object_key(key)
        local_path = _resolve_local_media_dir() / rel_key
        if local_path.exists():
            logger.info(
                "DEV: Reading GCS download for gs://%s/%s from %s",
                bucket_name,
                key,
                local_path,
            )
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
