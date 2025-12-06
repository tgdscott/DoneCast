from __future__ import annotations

import logging
import json
from typing import Any, Optional, cast

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import Session

from api.core.config import settings
from api.core.database import get_session
from api.core import crud
from api.core.redis_client import get_redis_client, redis_get, redis_setex
from api.models.user import User
from api.models.settings import load_admin_settings

logger = logging.getLogger(__name__)

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
    
    Uses Redis cache (45s TTL) to reduce DB hits during frequent polling.
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

    # Try Redis cache first to avoid DB hit
    redis_key = f"user:session:{email}"
    cached_data = redis_get(redis_key)
    
    if cached_data:
        try:
            user_data = json.loads(cached_data)
            # Reconstruct User object from cached data
            # We use User(**user_data) to map fields explicitly
            user = User(**user_data)
            
            # Check deleted status first (most critical security check)
            if user.is_deleted_view:
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
                if not user.is_admin:
                    detail: dict[str, Any] = {
                        "detail": "Service is temporarily unavailable for maintenance.",
                        "maintenance": True,
                    }
                    msg = getattr(admin_settings, "maintenance_message", None)
                    if msg:
                        detail["message"] = msg
                    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail)
            
            return user
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Failed to deserialize cached user for {email}: {e}")
            # Fall through to DB fetch

    # Fetch from DB
    user = crud.get_user_by_email(session=session, email=email)
    if not user:
        raise credentials_exception

    # Check deleted status
    if user.is_deleted_view:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deleted. Contact support@podcastplusplus.com to restore access during the grace period."
        )

    # Check maintenance mode
    try:
        admin_settings = load_admin_settings(session)
    except Exception:
        admin_settings = None
        
    if admin_settings and getattr(admin_settings, "maintenance_mode", False):
        if not user.is_admin:
            detail: dict[str, Any] = {
                "detail": "Service is temporarily unavailable for maintenance.",
                "maintenance": True,
            }
            msg = getattr(admin_settings, "maintenance_message", None)
            if msg:
                detail["message"] = msg
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail)

    # Cache user to Redis
    try:
        # Serialize user to JSON
        # Use .model_dump() if available (Pydantic v2) or .dict() (Pydantic v1)
        # We use default=str to handle UUID and datetime serialization
        if hasattr(user, "model_dump"):
            user_dict = user.model_dump()
        else:
            user_dict = user.dict()
            
        redis_setex(
            redis_key, 
            45, 
            json.dumps(user_dict, default=str)
        )
    except Exception as e:
        logger.warning(f"Failed to cache user {email} to Redis: {e}")

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
    required_version = getattr(settings, "TERMS_VERSION", None)
    
    # Access attributes directly - user is either attached (from DB) or fully populated (from Redis)
    accepted_version = user.terms_version_accepted
    user_email = user.email
    
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
