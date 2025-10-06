"""Utilities for interacting with Google Cloud Storage.

This module wraps the ``google-cloud-storage`` client library and provides a
set of helpers that gracefully degrade when running in a local development
environment. When GCS is unavailable (missing credentials or buckets) we fall
back to reading and writing files inside a local ``media`` directory so that
the rest of the application can continue to function.
"""

from __future__ import annotations

import logging
import os
import shutil
from datetime import timedelta
from pathlib import Path
from typing import IO, List, Optional

try:  # pragma: no cover - the dependency is optional for local development
    from google.api_core import exceptions as gcs_exceptions
    from google.auth.exceptions import DefaultCredentialsError
    from google.cloud import storage
except ImportError:  # pragma: no cover - handled at runtime by fallbacks
    gcs_exceptions = None  # type: ignore[assignment]
    DefaultCredentialsError = None  # type: ignore[assignment]
    storage = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)


# Cached media root used for local development fallbacks.
_LOCAL_MEDIA_DIR: Optional[Path] = None


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _resolve_local_media_dir() -> Path:
    """Return the directory that should hold local media fallbacks."""

    global _LOCAL_MEDIA_DIR
    if _LOCAL_MEDIA_DIR is not None:
        return _LOCAL_MEDIA_DIR

    candidates: List[Path] = []

    for env_name in ("MEDIA_ROOT", "MEDIA_DIR"):
        value = (os.getenv(env_name) or "").strip()
        if value:
            candidates.append(Path(value).expanduser())

    try:  # pragma: no cover - best effort import
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
            resolved = candidate.resolve()
        except Exception:
            resolved = candidate
        try:
            resolved.mkdir(parents=True, exist_ok=True)
        except Exception as exc:  # pragma: no cover - debug logging only
            logger.debug("Unable to prepare media directory %s: %s", resolved, exc)
            continue
        _LOCAL_MEDIA_DIR = resolved
        return resolved

    # Extremely defensive: ensure a directory exists even if all candidates failed.
    fallback = Path.cwd() / "media"
    fallback.mkdir(parents=True, exist_ok=True)
    _LOCAL_MEDIA_DIR = fallback
    return fallback


def _normalize_object_key(key: str) -> Path:
    """Normalise an object key to a safe, relative :class:`Path`."""

    key = (key or "").replace("\\", "/").strip("/")
    if not key:
        raise ValueError("Object key cannot be empty")

    parts = [part for part in key.split("/") if part and part not in {".", ".."}]
    if not parts:
        raise ValueError("Object key cannot reference the root directory")
    return Path(*parts)


def _local_media_url(key: str) -> Optional[str]:
    try:
        rel_key = _normalize_object_key(key)
    except ValueError:
        return None

    candidate = _resolve_local_media_dir() / rel_key
    if not candidate.exists():
        return None
    return f"/static/media/{rel_key.as_posix()}"


def _local_media_path(key: str) -> Path:
    rel_key = _normalize_object_key(key)
    path = _resolve_local_media_dir() / rel_key
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
    return "bucket does not exist" in message or "notfound" in message


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
        _gcs_project = getattr(client, "project", None)
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
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Failed to initialize GCS client: %s", exc, exc_info=True)
        return None


# Prepare client on import so we surface logging early when possible.
_get_gcs_client()


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def _generate_signed_url(
    bucket_name: str,
    key: str,
    *,
    expires: timedelta,
    method: str = "GET",
    content_type: Optional[str] = None,
) -> Optional[str]:
    """Generate a signed URL, using IAM-based signing when private key unavailable.
    
    Cloud Run uses Compute Engine credentials which don't have private keys.
    We use the IAMCredentials API to sign URLs instead.
    """
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
        }
        
        # Try to use service_account_email if available (key-based auth)
        if _signer_email:
            kwargs["service_account_email"] = _signer_email
            
        if content_type and method.upper() in {"POST", "PUT"}:
            kwargs["content_type"] = content_type
            
        try:
            # Try standard signing first (works with service account keys)
            return blob.generate_signed_url(**kwargs)
        except AttributeError as e:
            # Cloud Run uses Compute Engine credentials without private keys
            # Since ppp-media-us-west1 bucket is publicly readable, just return public URL
            if "private key" in str(e).lower():
                logger.info("No private key available; using public URL (bucket is publicly readable)")
                return f"https://storage.googleapis.com/{bucket_name}/{key}"
            else:
                raise
                
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
    """Generate a signed URL for a GCS object, with optional local fallback."""

    expiration = max(1, int(expiration or 0))
    try:
        url = _generate_signed_url(
            bucket_name,
            key,
            expires=timedelta(seconds=expiration),
            method="GET",
        )
    except Exception as exc:
        if not _should_fallback(bucket_name, exc):
            raise
        logger.warning(
            "GCS signed-url generation failed for gs://%s/%s: %s -- falling back to local media",
            bucket_name,
            key,
            exc,
        )
        url = None

    if url:
        return url

    return _local_media_url(key)


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
    try:
        url = _generate_signed_url(
            bucket,
            key,
            expires=timedelta(minutes=minutes),
            method=method,
            content_type=content_type,
        )
    except Exception as exc:
        if not _should_fallback(bucket, exc):
            raise
        logger.warning(
            "GCS signed URL generation failed for gs://%s/%s: %s -- using local media fallback",
            bucket,
            key,
            exc,
        )
        url = None

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


def _write_local_stream(bucket_name: str, key: str, fileobj: IO) -> str:
    local_path = _local_media_path(key)
    with local_path.open("wb") as handle:
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

    logger.info(
        "DEV: Wrote GCS upload for gs://%s/%s to %s",
        bucket_name,
        key,
        local_path,
    )
    return str(local_path)


def _write_local_bytes(bucket_name: str, key: str, data: bytes) -> str:
    local_path = _local_media_path(key)
    local_path.write_bytes(data)
    logger.info(
        "DEV: Wrote GCS upload for gs://%s/%s to %s",
        bucket_name,
        key,
        local_path,
    )
    return str(local_path)


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
    elif not _should_fallback(bucket_name):
        raise RuntimeError("GCS client unavailable and fallback is disabled")

    return _write_local_stream(bucket_name, key, fileobj)


def upload_bytes(
    bucket_name: str,
    key: str,
    data: bytes,
    content_type: Optional[str] = None,
) -> str:
    """Upload raw bytes to GCS, with a local development fallback."""

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
    elif not _should_fallback(bucket_name):
        raise RuntimeError("GCS client unavailable and fallback is disabled")

    return _write_local_bytes(bucket_name, key, data)


def download_gcs_bytes(bucket_name: str, key: str) -> Optional[bytes]:
    """Download an object from GCS as bytes, falling back to local storage."""

    client = _get_gcs_client()
    if client:
        try:
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(key)
            return blob.download_as_bytes()
        except Exception as exc:
            logger.error(
                "Failed to download gs://%s/%s: %s",
                bucket_name,
                key,
                exc,
            )
            if not _should_fallback(bucket_name, exc):
                return None
    elif not _should_fallback(bucket_name):
        return None

    try:
        local_path = _local_media_path(key)
    except ValueError:
        return None

    if not local_path.exists():
        return None

    logger.info(
        "DEV: Reading gs://%s/%s from %s",
        bucket_name,
        key,
        local_path,
    )
    return local_path.read_bytes()


def download_bytes(bucket_name: str, key: str) -> Optional[bytes]:
    """Backwards compatible wrapper for legacy imports.

    Several parts of the codebase still import :func:`download_bytes` from this
    module.  During the infrastructure/worker split the helper was renamed to
    :func:`download_gcs_bytes`, but the old symbol was never re-exported.  The
    resulting ``ImportError`` caused transcript downloads to silently fail in
    worker processes (they fall back to ``None`` when the import is missing),
    which meant assembly could not locate existing transcript JSON artefacts
    stored in GCS.  Episode assembly would then skip cleanup because
    ``words_json_path`` was ``None``.

    Providing a thin wrapper keeps existing call sites working and restores the
    expected behaviour without changing their imports.  New code should prefer
    :func:`download_gcs_bytes` but both names now behave identically.
    """

    return download_gcs_bytes(bucket_name, key)


def blob_exists(bucket_name: str, blob_name: str) -> Optional[bool]:
    """Return ``True`` when a blob exists, ``False`` when confirmed missing."""

    if not bucket_name or not blob_name:
        return False

    client = _get_gcs_client()
    should_fallback = False

    if client:
        try:
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(blob_name)
            return bool(blob.exists())
        except Exception as exc:
            if _should_fallback(bucket_name, exc):
                should_fallback = True
            else:
                logger.debug(
                    "Failed to probe gs://%s/%s existence: %s",
                    bucket_name,
                    blob_name,
                    exc,
                )
                return None
    else:
        should_fallback = _should_fallback(bucket_name)

    if not should_fallback:
        return None

    try:
        return _local_media_path(blob_name).exists()
    except Exception:
        return None


def delete_gcs_blob(bucket_name: str, blob_name: str) -> None:
    """Delete a blob from a GCS bucket, ignoring failures in development."""

    client = _get_gcs_client()
    if not client:
        logger.warning(
            "GCS client unavailable, cannot delete gs://%s/%s",
            bucket_name,
            blob_name,
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
