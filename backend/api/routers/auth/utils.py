"""Shared helpers for the authentication routers."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Mapping, Optional, cast

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import Session

from api.core import crud
from api.core.config import settings
from api.core.database import get_session
from api.core.security import verify_password
from api.limits import DISABLE as RL_DISABLED
from api.limits import limiter
from api.models.user import User, UserPublic

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")

try:  # pragma: no cover - executed only when python-jose is missing in prod builds
    from jose import JWTError, jwt
except ModuleNotFoundError as exc:  # pragma: no cover
    JWTError = Exception  # type: ignore[assignment]
    jwt = None  # type: ignore[assignment]
    JOSE_IMPORT_ERROR: Optional[ModuleNotFoundError] = exc
else:
    JOSE_IMPORT_ERROR = None

if TYPE_CHECKING:  # pragma: no cover - typing helper
    from authlib.integrations.starlette_client import OAuth as OAuthType
else:  # pragma: no cover - runtime alias for type checkers
    OAuthType = Any  # type: ignore[assignment]

try:  # pragma: no cover - executed only when authlib is missing in prod builds
    from authlib.integrations.starlette_client import OAuth as _OAuthFactory
except ModuleNotFoundError as exc:  # pragma: no cover
    _OAuthFactory = None  # type: ignore[assignment]
    AUTHLIB_ERROR: Optional[ModuleNotFoundError] = exc
else:
    AUTHLIB_ERROR = None


def raise_jwt_missing(context: str) -> None:
    """Raise a helpful HTTP error when python-jose is absent."""

    detail = (
        "Authentication service is misconfigured (missing JWT support). "
        "Please contact support."
    )
    if JOSE_IMPORT_ERROR:
        logger.error("JWT dependency missing while %s: %s", context, JOSE_IMPORT_ERROR)
    else:
        logger.error("JWT dependency missing while %s", context)
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)


def verify_password_or_error(password: str, hashed_password: str) -> bool:
    """Wrapper around verify_password that surfaces configuration errors cleanly."""

    try:
        return verify_password(password, hashed_password)
    except RuntimeError as exc:
        logger.error("Password verification unavailable: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service is misconfigured (password hashing unavailable).",
        )


def is_admin_email(email: str | None) -> bool:
    admin_email = getattr(settings, "ADMIN_EMAIL", "") or ""
    return bool(email and admin_email and email.lower() == admin_email.lower())


def create_access_token(data: Mapping[str, Any], expires_delta: timedelta | None = None) -> str:
    """Create a JWT access token."""

    if jwt is None:
        raise_jwt_missing("creating access tokens")
    to_encode = dict(data)
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    jwt_mod = cast(Any, jwt)
    encoded_jwt = jwt_mod.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def get_current_user(
    request: Request,
    session: Session = Depends(get_session),
    token: str = Depends(oauth2_scheme),
) -> User:
    """Decode the JWT token to get the current user."""

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if jwt is None:
        raise_jwt_missing("validating credentials")
    try:
        jwt_mod = cast(Any, jwt)
        payload = jwt_mod.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email = payload.get("sub")
        if not isinstance(email, str) or not email:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = crud.get_user_by_email(session=session, email=email)
    if user is None:
        raise credentials_exception
    return user


def to_user_public(user: User) -> UserPublic:
    """Build a safe public view from DB User without leaking hashed_password."""

    public = UserPublic.model_validate(user, from_attributes=True)
    public.is_admin = is_admin_email(user.email) or bool(getattr(user, "is_admin", False))
    public.terms_version_required = getattr(settings, "TERMS_VERSION", None)
    return public


def parse_forwarded_header(forwarded: str | None) -> tuple[str | None, str | None]:
    """Parse RFC 7239 Forwarded header minimally to extract proto and host."""

    if not forwarded:
        return None, None
    try:
        first = forwarded.split(",", 1)[0]
        parts = [p.strip() for p in first.split(";") if p.strip()]
        kv: dict[str, str] = {}
        for part in parts:
            if "=" in part:
                k, v = part.split("=", 1)
                kv[k.strip().lower()] = v.strip().strip('"')
        return kv.get("proto"), kv.get("host")
    except Exception:
        return None, None


def external_base_url(request: Request) -> str:
    """Determine the external base URL (scheme://host) for this request."""

    hdr = request.headers
    xf_proto = (hdr.get("x-forwarded-proto") or "").split(",")[0].strip()
    xf_host = (hdr.get("x-forwarded-host") or "").split(",")[0].strip()
    f_proto, f_host = parse_forwarded_header(hdr.get("forwarded"))

    host = xf_host or f_host or hdr.get("host") or request.url.hostname
    proto = xf_proto or f_proto or request.url.scheme or "https"

    try:
        import urllib.parse as _urlp

        base_cfg = (settings.OAUTH_BACKEND_BASE or "").strip()
        if base_cfg:
            parsed = _urlp.urlparse(base_cfg)
            if parsed.scheme and parsed.hostname and host:
                if parsed.hostname == host or host.endswith("podcastplusplus.com"):
                    proto = parsed.scheme
        if host and host.endswith("podcastplusplus.com") and proto != "https":
            proto = "https"
    except Exception:
        pass

    return f"{proto}://{host}".rstrip("/")


def build_oauth_client() -> tuple[OAuthType, str]:
    """Construct a new OAuth client registered for Google."""

    if _OAuthFactory is None:
        message = "Google OAuth is unavailable because authlib is not installed."
        if AUTHLIB_ERROR:
            logger.warning("%s Import error: %s", message, AUTHLIB_ERROR)
        else:
            logger.warning(message)
        raise RuntimeError(message)

    oauth_client = _OAuthFactory()
    oauth_client.register(
        name="google",
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        client_kwargs={"scope": "openid email profile"},
    )
    return oauth_client, settings.GOOGLE_CLIENT_ID


def ensure_admin_flag(user: User, session: Session | None = None) -> None:
    """Ensure the admin flag is synchronised when the email matches the ADMIN_EMAIL."""

    if is_admin_email(getattr(user, "email", None)) and not getattr(user, "is_admin", False):
        user.is_admin = True  # type: ignore[assignment]
        if session is not None:
            session.add(user)
            session.commit()
            session.refresh(user)


__all__ = [
    "AUTHLIB_ERROR",
    "JOSE_IMPORT_ERROR",
    "RL_DISABLED",
    "build_oauth_client",
    "create_access_token",
    "ensure_admin_flag",
    "external_base_url",
    "get_current_user",
    "is_admin_email",
    "limiter",
    "oauth2_scheme",
    "parse_forwarded_header",
    "raise_jwt_missing",
    "to_user_public",
    "verify_password_or_error",
]
