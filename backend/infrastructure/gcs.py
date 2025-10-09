"""Utilities for interacting with Google Cloud Storage.

This module wraps the ``google-cloud-storage`` client library and provides a
set of helpers that gracefully degrade when running in a local development
environment. When GCS is unavailable (missing credentials or buckets) we fall
back to reading and writing files inside a local ``media`` directory so that
the rest of the application can continue to function.
"""

from __future__ import annotations

import json
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
    from google.oauth2 import service_account
except ImportError:  # pragma: no cover - handled at runtime by fallbacks
    gcs_exceptions = None  # type: ignore[assignment]
    DefaultCredentialsError = None  # type: ignore[assignment]
    storage = None  # type: ignore[assignment]
    service_account = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)

# Cached signing credentials
_SIGNING_CREDENTIALS = None


def _get_signing_credentials():
    """Load service account credentials for signing URLs from Secret Manager or env var."""
    global _SIGNING_CREDENTIALS
    
    if _SIGNING_CREDENTIALS is not None:
        return _SIGNING_CREDENTIALS
    
    # Try loading from environment variable first (for local development)
    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if cred_path and os.path.exists(cred_path):
        try:
            credentials = service_account.Credentials.from_service_account_file(cred_path)
            _SIGNING_CREDENTIALS = credentials
            logger.info("Loaded signing credentials from GOOGLE_APPLICATION_CREDENTIALS")
            return credentials
        except Exception as e:
            logger.warning(f"Failed to load signing credentials from file: {e}")
    
    # Try loading from GCS_SIGNER_KEY_JSON env var (Cloud Run with Secret Manager)
    signer_key_json = os.getenv("GCS_SIGNER_KEY_JSON")
    if signer_key_json:
        try:
            # If it starts with sm://, Cloud Run will have already resolved it to the actual JSON content
            # Otherwise, treat it as inline JSON
            key_dict = json.loads(signer_key_json)
            credentials = service_account.Credentials.from_service_account_info(key_dict)
            _SIGNING_CREDENTIALS = credentials
            logger.info("Loaded signing credentials from GCS_SIGNER_KEY_JSON env var")
            return credentials
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse GCS_SIGNER_KEY_JSON as JSON: {e}")
        except Exception as e:
            logger.warning(f"Failed to load signing credentials from GCS_SIGNER_KEY_JSON: {e}")
    
    # Try loading from Secret Manager directly (fallback for Cloud Run)
    try:
        from google.cloud import secretmanager
        
        client = secretmanager.SecretManagerServiceClient()
        project_id = os.getenv("GCP_PROJECT", "podcast612")
        secret_name = f"projects/{project_id}/secrets/gcs-signer-key/versions/latest"
        
        response = client.access_secret_version(request={"name": secret_name})
        key_json = response.payload.data.decode("UTF-8")
        key_dict = json.loads(key_json)
        
        credentials = service_account.Credentials.from_service_account_info(key_dict)
        _SIGNING_CREDENTIALS = credentials
        logger.info("Loaded signing credentials from Secret Manager")
        return credentials
    except Exception as e:
        logger.warning(f"Failed to load signing credentials from Secret Manager: {e}")
        return None


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
        logger.warning("Local media file not found for key: %s (path: %s)", key, candidate)
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
    """Generate a signed URL, using service account credentials or IAM-based signing.
    
    Priority order:
    1. Try using loaded service account credentials (from env var or Secret Manager)
    2. Try using default client credentials
    3. Fall back to IAM-based signing for Cloud Run
    """
    client = _get_gcs_client()
    if not client:
        return None

    # Try using signing credentials from Secret Manager or env var first
    signing_creds = _get_signing_credentials()
    if signing_creds:
        try:
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(key)
            kwargs = {
                "version": "v4",
                "expiration": expires,
                "method": method,
                "credentials": signing_creds,
            }
            
            if content_type and method.upper() in {"POST", "PUT"}:
                kwargs["content_type"] = content_type
                
            signed_url = blob.generate_signed_url(**kwargs)
            logger.debug("Generated signed URL using loaded service account credentials")
            return signed_url
        except Exception as e:
            logger.warning(f"Failed to generate signed URL with loaded credentials: {e}")
            # Fall through to try other methods

    # Try standard signing with client credentials
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
            
        signed_url = blob.generate_signed_url(**kwargs)
        logger.debug("Generated signed URL using default client credentials")
        return signed_url
    except (AttributeError, ValueError) as e:
        # Cloud Run uses Compute Engine credentials without private keys
        error_str = str(e).lower()
        if "private key" in error_str or "signer" in error_str:
            # For write operations, try IAM-based signing
            if method.upper() != "GET":
                logger.info("No private key available; using IAM-based signing for %s", method)
                try:
                    from google.auth import compute_engine, iam
                    from google.auth.transport import requests as auth_requests
                    
                    # Get compute engine credentials
                    credentials = compute_engine.Credentials()
                    
                    # Create IAM signer that uses the IAM Credentials API
                    request = auth_requests.Request()
                    signer = iam.Signer(
                        request=request,
                        credentials=credentials,
                        service_account_email=None  # Will auto-detect from credentials
                    )
                    
                    # Generate signed URL using the IAM signer
                    from google.cloud.storage._signing import generate_signed_url_v4
                    
                    signed_url = generate_signed_url_v4(
                        credentials=signer,
                        resource=f"/{bucket_name}/{key}",
                        expiration=expires,
                        api_access_endpoint="https://storage.googleapis.com",
                        method=method,
                        headers={"Content-Type": content_type} if content_type else None,
                    )
                    
                    return signed_url
                    
                except Exception as iam_err:
                    logger.error("IAM-based signing failed: %s", iam_err, exc_info=True)
                    raise RuntimeError(f"Cannot generate signed {method} URL without private key or IAM access") from iam_err
            else:
                # For GET operations, return None to trigger fallback handling
                logger.warning("No private key available for GET request; will use fallback")
                return None
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


def get_public_audio_url(gcs_path: Optional[str], expiration_days: int = 7) -> Optional[str]:
    """
    Generate a public-accessible URL for podcast audio in GCS.
    
    For RSS feeds, generates signed URLs with longer expiration (default 7 days).
    Podcast apps cache RSS feeds, so URLs need to remain valid for several days.
    
    Args:
        gcs_path: Full GCS path like "gs://bucket/path/to/file.mp3"
        expiration_days: How many days the URL should remain valid (default 7)
        
    Returns:
        Public HTTPS URL for the audio file, or None if path is invalid
        
    Usage:
        >>> get_public_audio_url("gs://my-bucket/episodes/ep123.mp3")
        'https://storage.googleapis.com/my-bucket/episodes/ep123.mp3?...'
    """
    if not gcs_path or not gcs_path.startswith("gs://"):
        logger.warning("Invalid GCS path for audio URL: %s", gcs_path)
        return None
    
    # Parse gs://bucket/path -> bucket, path
    try:
        parts = gcs_path[5:].split("/", 1)
        if len(parts) != 2:
            logger.warning("Invalid GCS path format: %s", gcs_path)
            return None
        
        bucket_name, object_path = parts
        
        # Generate signed URL with expiration
        signed_url = _generate_signed_url(
            bucket_name=bucket_name,
            key=object_path,
            expires=timedelta(days=expiration_days),
            method="GET",
        )
        
        if signed_url:
            logger.debug("Generated public audio URL for %s (expires in %d days)", gcs_path, expiration_days)
            return signed_url
        
        # Fallback: Return public GCS URL (will only work if bucket is publicly readable)
        public_url = f"https://storage.googleapis.com/{bucket_name}/{object_path}"
        logger.warning("Could not generate signed URL, falling back to public URL: %s", public_url)
        return public_url
        
    except Exception as e:
        logger.error("Failed to generate public audio URL for %s: %s", gcs_path, e, exc_info=True)
        return None
