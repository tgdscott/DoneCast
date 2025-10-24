"""Dev environment safety middleware for Cloud SQL Proxy usage

Prevents accidental destructive operations when connecting to production database
via Cloud SQL Proxy in development mode.
"""
from fastapi import Request, HTTPException
from api.core.config import settings
import logging

log = logging.getLogger(__name__)


async def dev_read_only_middleware(request: Request, call_next):
    """
    Prevent destructive operations in dev read-only mode.
    
    When DEV_READ_ONLY=true in environment:
    - Blocks DELETE, PUT, PATCH, POST requests
    - Allows auth endpoints (login/register/verify)
    - Allows GET requests (safe browsing)
    
    This prevents accidentally modifying production data when using
    Cloud SQL Proxy for local development.
    """
    if settings.is_dev_mode and settings.DEV_READ_ONLY:
        # Allow read operations
        if request.method == "GET":
            return await call_next(request)
        
        # Allow auth endpoints even in read-only mode
        path = request.url.path
        if path.startswith("/api/auth"):
            return await call_next(request)
        
        # Block all write operations
        if request.method in ["DELETE", "PUT", "PATCH", "POST"]:
            log.warning(
                "[DEV_SAFETY] Blocked %s %s (read-only mode enabled)",
                request.method,
                path
            )
            raise HTTPException(
                status_code=403,
                detail=(
                    "Read-only mode enabled in dev environment. "
                    "Set DEV_READ_ONLY=false in .env.local to allow writes."
                )
            )
    
    return await call_next(request)
