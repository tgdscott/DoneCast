import logging
import os
import shutil
from datetime import timedelta
from pathlib import Path
from typing import IO, Optional, List

try:
    from google.cloud import storage
    from google.auth.exceptions import DefaultCredentialsError
    from google.api_core import exceptions as gcs_exceptions
except ImportError:  # pragma: no cover - optional dependency for local dev
    storage = None  # type: ignore[assignment]
    DefaultCredentialsError = None  # type: ignore[assignment]
    gcs_exceptions = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# Cached media root used for local development fallbacks.
_LOCAL_MEDIA_DIR: Optional[Path] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_media_dir() -> Path:
    """Return the directory used for local media fallbacks."""

    global _LOCAL_MEDIA_DIR
    if _LOCAL_MEDIA_DIR is not None:
        return _LOCAL_MEDIA_DIR

    candidates: List[Path] = []

    for env_name in ("MEDIA_ROOT", "MEDIA_DIR"):
        value = (os.getenv(env_name) or "").strip()
        if value:
            candidates.append(Path(value).expanduser())

    try:
        from api.core.paths import MEDIA_DIR as API_MEDIA_DIR  # type: ignore

        if isinstance(API_MEDIA_DIR, Path):
            candidates.append(API_MEDIA_DIR)
        elif API_MEDIA_DIR:
            candidates.append(Path(API_MEDIA_DIR))
    except Exception:
        pass

    # Final fallbacks live alongside the application for dev runs.
    candidates.append(Path("local_media"))
    candidates.append(Path("media"))

    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            logger.debug("Unable to prepare media directory %s: %s", candidate, exc)
            continue
        _LOCAL_MEDIA_DIR = candidate
        return candidate

    # Extremely defensive: ensure a directory exists even if all candidates failed.
    fallback = Path.cwd() / "media"
    fallback.mkdir(parents=True, exist_ok=True)
    _LOCAL_MEDIA_DIR = fallback
    return fallback


def _normalise_key(key: str) -> Path:
    key = (key or "").replace("\\", "/").strip("/")
    if not key:
        raise ValueError("Object key cannot be empty")
    parts = [part for part in key.split("/") if part and part not in {".", ".."}]
    return Path(*parts)


def _local_media_url(key: str) -> Optional[str]:
    try:
        rel_key = _normalise_key(key)
    except ValueError:
        return None

    candidate = _resolve_media_dir() / rel_key
    if not candidate.exists():
        return None
    return f"/static/media/{rel_key.as_posix()}"


def _local_media_path(key: str) -> Path:
    rel_key = _normalise_key(key)
    path = _resolve_media_dir() / rel_key
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _is_dev_env() -> bool:
    env = (
        os.getenv("APP_ENV")
        or os.getenv("ENV")
        or os.getenv("PYTHON_ENV")
        or ""
    ).strip().lower()
    if not env:
        return True  # Treat unset as development for local runs.
    return env in {"dev", "development", "local", "test", "testing"}


def _looks_like_local_bucket(bucket_name: str) -> bool:
    lowered = bucket_name.lower()
    return any(marker in lowered for marker in ("local", "dev"))


def _should_fallback(bucket_name: str, exc: Optional[Exception] = None) -> bool:
    if not (_is_dev_env() or _looks_like_local_bucket(bucket_name)):
        return False

    if exc is None:
        return True

    if gcs_exceptions is not None and isinstance(exc, gcs_exceptions.NotFound):
        return True

    message = str(exc).lower()
    if "bucket does not exist" in message or "notfound" in message:
        return True

    return False


# ---------------------------------------------------------------------------
# GCS client initialisation
# ---------------------------------------------------------------------------

_gcs_client = None
_gcs_credentials = None
_gcs_project = None
_signer_email = None


def _get_gcs_client():
    """Initialise and return a GCS client, handling credentials gracefully."""

    global _gcs_client, _gcs_credentials, _gcs_project, _signer_email

    if _gcs_client:
        return _gcs_client

    if not storage:
        logger.debug("GCS client requested but google-cloud-storage is unavailable")
        return None

    try:
        client = storage.Client()
        _gcs_client = client
        _gcs_credentials = getattr(client, "_credentials", None)
        _gcs_project = client.project
        if hasattr(_gcs_credentials, "service_account_email"):
            _signer_email = _gcs_credentials.service_account_email
        logger.info(
            "GCS client initialized for project %s. Signer: %s",
            _gcs_project,
            _signer_email or "N/A (will use key if available)",
        )
        return _gcs_client
    except DefaultCredentialsError:  # type: ignore[unreachable]
        logger.warning("GCS credentials not found. GCS operations will be disabled.")
        return None
    except Exception as exc:
        logger.error("Failed to initialize GCS client: %s", exc, exc_info=True)
        return None


# Prepare client on import so we surface logging early when possible.
_get_gcs_client()


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get_signed_url(bucket_name: str, key: str, expiration: int = 3600) -> Optional[str]:
    """Generate a signed URL for a GCS object."""

    client = _get_gcs_client()
    if not client:
        return None

    try:
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(key)
        return blob.generate_signed_url(
            version="v4",
            expiration=timedelta(seconds=max(1, int(expiration or 0))),
            method="GET",
            service_account_email=_signer_email,
        )
    except Exception as exc:
        logger.error(
            "Failed to sign URL for gs://%s/%s: %s",
            bucket_name,
            key,
            exc,
            exc_info=True,
        )
        raise


def make_signed_url(
    bucket: str,
    key: str,
    minutes: int = 60,
    *,
    method: str = "GET",
    content_type: Optional[str] = None,
) -> str:
    """Return a signed URL or a local fallback for the given object."""

    client = _get_gcs_client()
    if client:
        try:
            bucket_obj = client.bucket(bucket)
            blob = bucket_obj.blob(key)
            return blob.generate_signed_url(
                version="v4",
                expiration=timedelta(minutes=max(1, int(minutes or 0))),
                method=method,
                service_account_email=_signer_email,
                content_type=content_type,
            )
        except Exception as exc:
            if not _should_fallback(bucket, exc):
                raise
            logger.warning(
                "GCS signed URL generation failed for gs://%s/%s: %s -- falling back to local media",
                bucket,
                key,
                exc,
            )
    else:
        if not _should_fallback(bucket):
            raise RuntimeError("GCS client unavailable and fallback is disabled")

    fallback = _local_media_url(key)
    if fallback:
        return fallback

    raise RuntimeError(f"Unable to locate gs://{bucket}/{key} for preview")


def upload_fileobj(
    bucket_name: str,
    key: str,
    fileobj: IO,
    content_type: Optional[str] = None,
    **kwargs,
) -> str:
    """Upload a file-like object to GCS, with a local development fallback."""

    client = _get_gcs_client()
    if client:
        try:
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(key)
            blob.upload_from_file(fileobj, content_type=content_type)
            logger.info("Uploaded to gs://%s/%s", bucket_name, key)
            return f"gs://{bucket_name}/{key}"
        except Exception as exc:
            if not _should_fallback(bucket_name, exc):
                raise
            logger.warning(
                "GCS upload failed for gs://%s/%s: %s -- writing to local media",
                bucket_name,
                key,
                exc,
            )
            try:
                if hasattr(fileobj, "seek"):
                    fileobj.seek(0)
            except Exception:
                pass
    else:
        if not _should_fallback(bucket_name):
            raise RuntimeError("GCS client unavailable and fallback is disabled")

    local_path = _local_media_path(key)
    with open(local_path, "wb") as handle:
        try:
            if hasattr(fileobj, "seek"):
                fileobj.seek(0)
        except Exception:
            pass
        shutil.copyfileobj(fileobj, handle)

    try:
        if hasattr(fileobj, "seek"):
            fileobj.seek(0)
    except Exception:
        pass

    logger.info("DEV: wrote upload for gs://%s/%s to %s", bucket_name, key, local_path)
    return str(local_path)


def upload_bytes(
    bucket_name: str,
    key: str,
    data: bytes,
    content_type: Optional[str] = None,
) -> str:
    """Upload bytes to GCS, with a local development fallback."""

    client = _get_gcs_client()
    if client:
        try:
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(key)
            blob.upload_from_string(data, content_type=content_type)
            logger.info("Uploaded to gs://%s/%s", bucket_name, key)
            return f"gs://{bucket_name}/{key}"
        except Exception as exc:
            if not _should_fallback(bucket_name, exc):
                raise
            logger.warning(
                "GCS upload failed for gs://%s/%s: %s -- writing to local media",
                bucket_name,
                key,
                exc,
            )
    else:
        if not _should_fallback(bucket_name):
            raise RuntimeError("GCS client unavailable and fallback is disabled")

    local_path = _local_media_path(key)
    local_path.write_bytes(data)
    logger.info("DEV: wrote upload for gs://%s/%s to %s", bucket_name, key, local_path)
    return str(local_path)


def download_gcs_bytes(bucket_name: str, key: str) -> Optional[bytes]:
    """Download an object from GCS as bytes, falling back to local storage."""

    client = _get_gcs_client()
    if client:
        try:
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(key)
            return blob.download_as_bytes()
        except Exception as exc:
            logger.error("Failed to download gs://%s/%s: %s", bucket_name, key, exc)
            if not _should_fallback(bucket_name, exc):
                return None
    elif not _should_fallback(bucket_name):
        return None

    try:
        rel_key = _normalise_key(key)
    except ValueError:
        return None

    local_path = _resolve_media_dir() / rel_key
    if not local_path.exists():
        return None

    logger.info(
        "DEV: reading gs://%s/%s from %s",
        bucket_name,
        key,
        local_path,
    )
    return local_path.read_bytes()


def delete_gcs_blob(bucket_name: str, blob_name: str) -> None:
    """Delete a blob from a GCS bucket, ignoring failures in development."""

    client = _get_gcs_client()
    if not client:
        logger.warning(
            "GCS client unavailable, cannot delete gs://%s/%s", bucket_name, blob_name
        )
        return

    try:
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.delete()
        logger.info("Deleted gs://%s/%s", bucket_name, blob_name)
    except Exception as exc:
        if _should_fallback(bucket_name, exc):
            logger.warning(
                "Ignoring delete failure for gs://%s/%s in local fallback: %s",
                bucket_name,
                blob_name,
                exc,
            )
            return
        logger.error(
            "Failed to delete gs://%s/%s: %s",
            bucket_name,
            blob_name,
            exc,
        )
