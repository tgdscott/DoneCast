from __future__ import annotations

import logging
from typing import Optional

try:
    from passlib.context import CryptContext
except ModuleNotFoundError as exc:  # pragma: no cover - exercised in misconfigured deploys
    CryptContext = None  # type: ignore[assignment]
    _PASSLIB_ERROR: Optional[ModuleNotFoundError] = exc
else:  # pragma: no cover - thin wrapper around passlib
    _PASSLIB_ERROR = None

log = logging.getLogger(__name__)

# Use bcrypt for hashing, which is a standard and secure choice.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto") if CryptContext else None


def _raise_passlib_missing() -> None:
    """Raise a helpful error when passlib is unavailable."""

    message = (
        "Password hashing library 'passlib' is not installed. "
        "Install passlib[bcrypt] to enable authentication."
    )
    if _PASSLIB_ERROR:
        raise RuntimeError(message) from _PASSLIB_ERROR
    raise RuntimeError(message)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against a hashed one."""

    if pwd_context is None:
        _raise_passlib_missing()

    try:
        # Return False for unknown/legacy hashes instead of raising, so callers send 401 not 500
        return pwd_context.verify(plain_password, hashed_password)
    except Exception as exc:  # broad: passlib may raise for unknown/invalid hashes
        try:
            preview = (hashed_password or "")[:10]
        except Exception:
            preview = ""
        log.warning(
            "verify_password failed (invalid/unknown hash); returning False: %s (hash=%s…)",
            type(exc).__name__,
            preview,
        )
        return False


def get_password_hash(password: str) -> str:
    """Hashes a plain password."""

    if pwd_context is None:
        _raise_passlib_missing()
    return pwd_context.hash(password)
