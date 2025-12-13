"""Shared helpers for the authentication routers."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Mapping, Optional, cast

from fastapi import HTTPException, Request, status
from sqlmodel import Session

from api.core import crud
from api.core.config import settings
from api.core.database import get_session
from api.core.security import verify_password
from api.limits import DISABLE as RL_DISABLED
from api.limits import limiter
from api.models.user import User, UserPublic
from api.core.auth import (
    get_current_user as core_get_current_user,
    oauth2_scheme as core_oauth2_scheme,
)

logger = logging.getLogger(__name__)

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


def is_superadmin(user: Any) -> bool:
    """Check if user has superadmin role."""
    return str(getattr(user, "role", "")).lower() == "superadmin"


def is_admin(user: Any) -> bool:
    """Check if user has admin or superadmin role (or legacy is_admin flag)."""
    role = str(getattr(user, "role", "")).lower()
    is_flag = bool(getattr(user, "is_admin", False))
    email_ok = is_admin_email(getattr(user, "email", None))
    return role in ("admin", "superadmin") or is_flag or email_ok


def get_user_role(user: Any) -> str:
    """Get user's role. Returns 'superadmin', 'admin', or 'user'."""
    role = str(getattr(user, "role", "")).lower()
    if role == "superadmin":
        return "superadmin"
    if role == "admin":
        return "admin"
    # Check legacy flags
    if is_admin_email(getattr(user, "email", None)):
        return "superadmin"  # ADMIN_EMAIL gets superadmin role
    if getattr(user, "is_admin", False):
        return "admin"  # Legacy is_admin flag gets admin role
    return "user"


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


oauth2_scheme = core_oauth2_scheme

# ``get_current_user`` in ``api.core.auth`` performs additional checks (such
# as maintenance mode enforcement).  Re-export it here so FastAPI dependencies
# across the codebase share the exact same callable, which also simplifies
# overriding the dependency in tests.
get_current_user = core_get_current_user


def _parse_terms_version_date(version_str: str | None) -> datetime | None:
    """Parse TERMS_VERSION string (e.g., '2025-10-22') as a date.
    
    Returns None if version_str is None or cannot be parsed.
    """
    if not version_str:
        return None
    try:
        # TERMS_VERSION is in format 'YYYY-MM-DD', parse as date and convert to datetime at midnight UTC
        from datetime import date
        parsed_date = datetime.strptime(version_str.strip(), "%Y-%m-%d").date()
        return datetime.combine(parsed_date, datetime.min.time()).replace(tzinfo=None)
    except (ValueError, AttributeError):
        logger.warning(f"Failed to parse TERMS_VERSION as date: {version_str}")
        return None


def _terms_need_acceptance(user: User, current_terms_version: str | None) -> bool:
    """Check if user needs to accept updated terms based on date comparison.
    
    Returns True if:
    - Current terms version date is newer than user's terms_accepted_at date, OR
    - User has never accepted terms (both terms_version_accepted and terms_accepted_at are None), OR
    - Version strings don't match (fallback if date parsing fails or date is missing)
    """
    if not current_terms_version:
        return False
    
    accepted_version = getattr(user, "terms_version_accepted", None)
    user_accepted_at = getattr(user, "terms_accepted_at", None)
    
    # If user has never accepted any version, they need to accept
    if not accepted_version and not user_accepted_at:
        return True
    
    # Try date-based comparison first (most accurate)
    current_terms_date = _parse_terms_version_date(current_terms_version)
    if current_terms_date and user_accepted_at:
        # Both dates are available - compare them
        # Handle case where user_accepted_at might be a string (from some DB serialization paths)
        if isinstance(user_accepted_at, str):
            try:
                user_accepted_at = datetime.fromisoformat(user_accepted_at.replace('Z', '+00:00'))
            except Exception:
                logger.warning(f"Failed to parse terms_accepted_at string: {user_accepted_at}")
                # Can't parse - fallback to version check
                if accepted_version:
                    return accepted_version != current_terms_version
                return True
        
        # user_accepted_at is now a datetime object
        try:
            user_accepted_naive = user_accepted_at.replace(tzinfo=None) if hasattr(user_accepted_at, 'replace') else user_accepted_at
            return current_terms_date > user_accepted_naive
        except Exception as e:
            logger.warning(f"Failed to compare terms dates: {e}")
            return True
    
    # Fallback to version string comparison if:
    # - Date parsing failed, OR
    # - User has version but no date (legacy data)
    if accepted_version:
        return accepted_version != current_terms_version
    
    # If we get here, user has no version string but might have a date (unlikely)
    # Default to requiring acceptance for safety
    return True


def to_user_public(user: User) -> UserPublic:
    """Build a safe public view from DB User without leaking hashed_password."""
    
    # DEBUG: Log what we're getting from the database
    db_role = getattr(user, "role", None)
    logger.info(f"[to_user_public] DB user {user.email}: role={db_role}, tier={user.tier}, is_admin={user.is_admin}")

    public = UserPublic.model_validate(user, from_attributes=True)
    
    # DEBUG: Log what model_validate gave us
    logger.info(f"[to_user_public] After model_validate: role={public.role}")
    
    # CRITICAL: Force the role field from DB (model_validate is broken)
    public.role = db_role
    logger.info(f"[to_user_public] After forcing role from DB: role={public.role}")
    
    # Set is_admin flag (legacy support)
    public.is_admin = is_admin_email(user.email) or bool(getattr(user, "is_admin", False))
    
    # Check if terms need acceptance based on date comparison
    env = (settings.APP_ENV or "dev").strip().lower()
    current_terms_version = getattr(settings, "TERMS_VERSION", None)
    
    if env in {"dev", "development", "local", "test", "testing"}:
        # Skip terms enforcement in dev mode
        public.terms_version_required = None
    elif current_terms_version and _terms_need_acceptance(user, current_terms_version):
        # Terms need to be accepted - set required version
        public.terms_version_required = current_terms_version
    else:
        # Terms are up to date or no terms version set
        public.terms_version_required = None
    
    logger.info(f"[to_user_public] Final result: role={public.role}, is_admin={public.is_admin}, terms_required={public.terms_version_required}")
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
    """Determine the external base URL (scheme://host) without leaking app/api subdomains.

    Behavior:
    - If the request appears to target a local/dev host (localhost, 127.0.0.1, or RFC1918
      private LAN ranges), we ALWAYS honor the incoming host and never override with
      a production-configured OAUTH_BACKEND_BASE.
    - Otherwise, if OAUTH_BACKEND_BASE is configured, prefer its scheme/host to build
      redirects consistently behind proxies or Cloud Run.
    - Force https scheme for our public production domains.
    """

    hdr = request.headers
    xf_proto = (hdr.get("x-forwarded-proto") or "").split(",")[0].strip()
    xf_host = (hdr.get("x-forwarded-host") or "").split(",")[0].strip()
    f_proto, f_host = parse_forwarded_header(hdr.get("forwarded"))

    host = xf_host or f_host or hdr.get("host") or request.url.hostname
    proto = xf_proto or f_proto or request.url.scheme or "https"

    def _is_local(h: str | None) -> bool:
        if not h:
            return False
        try:
            import ipaddress as _ip
            name = h.split(":", 1)[0].strip().lower()
            if name in {"localhost"}:
                return True
            try:
                ip = _ip.ip_address(name)
                return ip.is_private or ip.is_loopback
            except ValueError:
                # Not an IP, treat common dev hostnames as local
                return name.endswith(".local")
        except Exception:
            return False

    try:
        import urllib.parse as _urlp

        base_cfg = (settings.OAUTH_BACKEND_BASE or "").strip()
        # Only apply configured backend base if host is not local/dev
        if base_cfg and not _is_local(str(host)):
            parsed = _urlp.urlparse(base_cfg)
            if parsed.scheme and parsed.hostname:
                host = parsed.hostname
                proto = parsed.scheme
        # Enforce https for our production domains
        if isinstance(host, str) and host.endswith(("podcastplusplus.com", "getpodcastplus.com")) and proto != "https":
            proto = "https"
    except Exception:
        pass

    return f"{proto}://{host}".rstrip("/")


# Global cache for OAuth client to avoid repeated metadata fetching
_oauth_client_cache: tuple[OAuthType, str] | None = None


def build_oauth_client() -> tuple[OAuthType, str]:
    """Construct a new OAuth client registered for Google with custom timeout.
    
    Caches the OAuth client globally since Google's metadata rarely changes and
    fetching it on every request causes 30+ second delays on slow networks.
    """
    global _oauth_client_cache
    
    # Return cached client if available
    if _oauth_client_cache is not None:
        logger.debug("OAuth: Returning cached OAuth client")
        return _oauth_client_cache

    if _OAuthFactory is None:
        message = "Google OAuth is unavailable because authlib is not installed."
        if AUTHLIB_ERROR:
            logger.warning("%s Import error: %s", message, AUTHLIB_ERROR)
        else:
            logger.warning(message)
        raise RuntimeError(message)

    # Check for required env vars before attempting OAuth client setup
    client_id = getattr(settings, 'GOOGLE_CLIENT_ID', '') or ''
    client_secret = getattr(settings, 'GOOGLE_CLIENT_SECRET', '') or ''
    
    if not client_id or not client_secret:
        message = f"Google OAuth not configured (GOOGLE_CLIENT_ID={'set' if client_id else 'missing'}, GOOGLE_CLIENT_SECRET={'set' if client_secret else 'missing'})"
        logger.error("[OAUTH] %s", message)
        raise RuntimeError(message)

    # Create custom httpx client with longer timeout to handle slow network/firewall
    try:
        import httpx
        custom_client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=15.0),  # 30s total, 15s connect
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        )
        logger.info("OAuth: Created custom httpx client with 30s timeout")
    except Exception as exc:
        logger.warning("Failed to create custom httpx client, using defaults: %s", exc)
        custom_client = None

    oauth_client = _OAuthFactory()
    
    # Configure the OAuth client with custom httpx client if available
    register_kwargs = {
        "name": "google",
        "server_metadata_url": "https://accounts.google.com/.well-known/openid-configuration",
        "client_id": client_id,
        "client_secret": client_secret,
        "client_kwargs": {"scope": "openid email profile"},
    }
    
    # Authlib's AsyncClient accepts a custom httpx client via the 'client' parameter
    if custom_client:
        register_kwargs["client"] = custom_client
    
    oauth_client.register(**register_kwargs)
    
    # Cache the client for future requests
    _oauth_client_cache = (oauth_client, client_id)
    logger.info("OAuth: Client initialized and cached")
    
    return oauth_client, client_id


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
