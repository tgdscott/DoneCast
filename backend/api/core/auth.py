from __future__ import annotations

import logging
import time
from typing import Any, Optional, cast
from collections import OrderedDict

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import Session
from sqlalchemy.orm.exc import DetachedInstanceError

from api.core.config import settings
from api.core.database import get_session
from api.core import crud
from api.models.user import User
from api.models.settings import load_admin_settings

logger = logging.getLogger(__name__)

# In-process cache for authenticated users to reduce DB hits during polling
# Cache keyed by JWT token (email from payload), with 45-second TTL
# This helps reduce connection pressure during spike windows when UI polls frequently
_USER_CACHE: OrderedDict[str, tuple[User, float]] = OrderedDict()
_USER_CACHE_TTL = 45.0  # 45 seconds - balance between freshness and DB load reduction
_USER_CACHE_MAX_SIZE = 1000  # Limit cache size to prevent memory issues


def _clean_user_cache() -> None:
    """Remove expired entries from user cache."""
    current_time = time.time()
    expired_keys = [
        key for key, (_, expiry) in _USER_CACHE.items()
        if expiry < current_time
    ]
    for key in expired_keys:
        _USER_CACHE.pop(key, None)


def _get_cached_user(email: str) -> Optional[User]:
    """Get user from cache if valid, None otherwise.
    
    Cache keyed by email only - for polling scenarios, the same user makes
    multiple requests in quick succession, so email-based caching is sufficient.
    """
    _clean_user_cache()
    cache_key = email.lower().strip()  # Normalize email for cache key
    if cache_key in _USER_CACHE:
        user, expiry = _USER_CACHE[cache_key]
        if expiry > time.time():
            # Move to end (LRU) - update access order
            _USER_CACHE.move_to_end(cache_key)
            return user
        else:
            _USER_CACHE.pop(cache_key, None)
    return None


def _cache_user(email: str, user: User, session: Optional[Session] = None) -> None:
    """Cache user for future requests.
    
    CRITICAL: Load all required attributes and expunge the user instance from the session.
    This creates a detached instance with all attributes in memory, preventing
    DetachedInstanceError when accessing attributes after the session closes.
    
    If session is None, the user is already expunged (caller's responsibility).
    """
    _clean_user_cache()
    cache_key = email.lower().strip()
    expiry = time.time() + _USER_CACHE_TTL
    
    # Enforce max size using LRU eviction
    if len(_USER_CACHE) >= _USER_CACHE_MAX_SIZE:
        _USER_CACHE.popitem(last=False)  # Remove oldest (first) item
    
    # CRITICAL: Eagerly access ALL attributes we'll need later while session is active
    # This loads them into the instance's __dict__ so they're available after detaching
    _ = user.is_deleted_view
    _ = user.is_admin
    _ = user.email
    _ = user.id
    _ = user.role
    _ = user.terms_version_accepted
    _ = user.tier
    _ = user.is_active
    
    # CRITICAL: Expunge the instance from the session to detach it
    # This ensures it won't try to lazy-load attributes after session closes
    # The attributes we accessed above are now in memory and will remain accessible
    if session is not None:
        try:
            session.expunge(user)
        except Exception as e:
            # If expunge fails, log but don't fail - the attributes are still loaded
            logger.warning("Failed to expunge user from session during cache: %s", e)
    
    _USER_CACHE[cache_key] = (user, expiry)

# Local OAuth2 scheme used for dependency token extraction
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")

try:  # pragma: no cover - optional in some builds
    from jose import JWTError, jwt
except ModuleNotFoundError as exc:  # pragma: no cover
    JWTError = Exception  # type: ignore[assignment]
    jwt = None  # type: ignore[assignment]
    _JOSE_IMPORT_ERROR: Optional[ModuleNotFoundError] = exc
else:
    _JOSE_IMPORT_ERROR = None


def _raise_jwt_missing(context: str) -> None:
    detail = (
        "Authentication service is misconfigured (missing JWT support). "
        "Please contact support."
    )
    if _JOSE_IMPORT_ERROR:
        logger.error("JWT dependency missing while %s: %s", context, _JOSE_IMPORT_ERROR)
    else:
        logger.error("JWT dependency missing while %s", context)
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)


async def get_current_user(
    request: Request,
    session: Session = Depends(get_session),
    token: str = Depends(oauth2_scheme),
) -> User:
    """Decode the JWT and return the current user or raise 401.
    
    Uses an in-process cache (45s TTL) to reduce DB hits during frequent polling.
    This helps reduce connection pressure during spike windows when the UI polls
    /api/notifications/ and /api/episodes/ concurrently.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if jwt is None:
        _raise_jwt_missing("validating credentials")
    try:
        jwt_mod = cast(Any, jwt)
        payload = jwt_mod.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email = payload.get("sub")
        if not isinstance(email, str) or not email:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    # Try cache first to avoid DB hit
    cached_user = _get_cached_user(email)
    if cached_user is not None:
        # Safely extract critical attribute values from cached user
        # We need to handle DetachedInstanceError in case attributes aren't accessible
        try:
            # Try to access attributes - if this fails, we'll refetch from DB
            cached_is_deleted = cached_user.is_deleted_view
            cached_is_admin = cached_user.is_admin
        except DetachedInstanceError:
            # Cache entry is problematic - invalidate and refetch
            logger.warning(
                "DetachedInstanceError on cached user %s - invalidating cache and refetching from DB",
                email
            )
            cache_key = email.lower().strip()
            _USER_CACHE.pop(cache_key, None)
            cached_user = None
            cached_is_deleted = None
            cached_is_admin = None
        
        if cached_user is not None and cached_is_deleted is not None:
            # We successfully extracted values from cached user
            # Check deleted status first (most critical security check)
            if cached_is_deleted:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="This account has been deleted. Contact support@podcastplusplus.com to restore access during the grace period."
                )
            
            # Check maintenance mode (requires DB query, but infrequent)
            try:
                admin_settings = load_admin_settings(session)
            except Exception:
                admin_settings = None
            if admin_settings and getattr(admin_settings, "maintenance_mode", False):
                # Use the cached is_admin value we already extracted
                if not cached_is_admin:
                    detail: dict[str, Any] = {
                        "detail": "Service is temporarily unavailable for maintenance.",
                        "maintenance": True,
                    }
                    msg = getattr(admin_settings, "maintenance_message", None)
                    if msg:
                        detail["message"] = msg
                    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail)
            
            # Return the cached user - it's been validated and values extracted
            return cached_user

    # Cache miss - fetch from DB
    user = crud.get_user_by_email(session=session, email=email)
    if user is None:
        raise credentials_exception
    
    # Block users who have requested account deletion (soft-deleted view)
    if getattr(user, "is_deleted_view", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deleted. Contact support@podcastplusplus.com to restore access during the grace period."
        )
    
    try:
        admin_settings = load_admin_settings(session)
    except Exception:
        admin_settings = None
    if admin_settings and getattr(admin_settings, "maintenance_mode", False):
        if not getattr(user, "is_admin", False):
            detail: dict[str, Any] = {
                "detail": "Service is temporarily unavailable for maintenance.",
                "maintenance": True,
            }
            msg = getattr(admin_settings, "maintenance_message", None)
            if msg:
                detail["message"] = msg
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail)

    # Cache the user for future requests
    # Strategy: Load all attributes, expunge for caching, then get a fresh instance to return
    # This ensures the cached user is properly detached with all attributes loaded,
    # while the returned user stays attached to the current session
    
    user_id = user.id  # Save ID before expunging
    
    # Load all attributes while session is active
    _ = user.is_deleted_view
    _ = user.is_admin
    _ = user.email
    _ = user.id
    _ = user.role
    _ = user.terms_version_accepted
    _ = user.tier
    _ = user.is_active
    
    try:
        # Expunge the user to detach it for caching
        session.expunge(user)
        
        # Cache the expunged user (all attributes are loaded, so they'll be accessible)
        _cache_user(email, user, session=None)
        
        # Get a fresh instance attached to the current session for returning
        # This ensures the returned user is properly attached and can be used in the request
        user_to_return = session.get(User, user_id)
        if user_to_return is None:
            # Fallback: if get() fails, just return the expunged user
            # It won't be attached, but attributes are loaded, so it should work
            logger.warning("Failed to get fresh user instance for return, using expunged user")
            return user
        
        return user_to_return
    except Exception as e:
        # If expunging/caching fails, log but don't fail the request
        # Just return the user as-is (it's still attached)
        logger.warning("Failed to cache user: %s", e)
        return user


async def get_current_user_with_terms(
    request: Request,
    session: Session = Depends(get_session),
    token: str = Depends(oauth2_scheme),
) -> User:
    """
    Get current user and enforce Terms of Service acceptance.
    
    Use this dependency for endpoints that should be blocked if user hasn't accepted terms.
    Exempted endpoints: /api/auth/*, /api/users/me, terms acceptance endpoints
    """
    user = await get_current_user(request=request, session=session, token=token)
    
    # Check if endpoint should be exempted from terms enforcement
    path = request.url.path
    exempted_paths = [
        '/api/auth/',
        '/api/users/me',
        '/api/admin/',  # Admin endpoints exempt
    ]
    
    if any(path.startswith(prefix) for prefix in exempted_paths):
        return user
    
    # Enforce terms acceptance for all other endpoints
    # Safely access user attributes in case user came from cache and is detached
    required_version = getattr(settings, "TERMS_VERSION", None)
    try:
        accepted_version = user.terms_version_accepted
        user_email = user.email
    except DetachedInstanceError:
        # If we get DetachedInstanceError, refetch user from DB
        # This shouldn't happen if _cache_user properly loads attributes, but be defensive
        logger.warning("DetachedInstanceError accessing user attributes in get_current_user_with_terms - refetching from DB")
        try:
            jwt_mod = cast(Any, jwt)
            payload = jwt_mod.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            email = payload.get("sub")
            if isinstance(email, str) and email:
                user = crud.get_user_by_email(session=session, email=email)
                if user:
                    accepted_version = user.terms_version_accepted
                    user_email = user.email
                else:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Could not validate credentials"
                    )
            else:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Could not validate credentials"
                )
        except Exception as e:
            logger.error("Failed to refetch user after DetachedInstanceError: %s", e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error"
            )
    
    if required_version and required_version != accepted_version:
        logger.warning(
            "[Terms Enforcement] Blocking user %s - terms not accepted (required: %s, accepted: %s)",
            user_email,
            required_version,
            accepted_version
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "Terms acceptance required",
                "message": "Please refresh your browser and accept the latest Terms of Use to continue.",
                "required_version": required_version,
                "accepted_version": accepted_version,
            }
        )
    
    return user


__all__ = ["get_current_user", "get_current_user_with_terms", "oauth2_scheme"]
