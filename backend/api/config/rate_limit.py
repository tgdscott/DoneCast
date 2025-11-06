"""Rate limiting configuration for the FastAPI application."""
from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from fastapi import FastAPI


def configure_rate_limiting(app: FastAPI) -> None:
    """Configure rate limiting middleware.
    
    Args:
        app: FastAPI application instance
    """
    from api.limits import limiter, DISABLE as RL_DISABLED
    
    # Rate limiting (if enabled)
    try:
        from slowapi.middleware import SlowAPIMiddleware
        from slowapi.errors import RateLimitExceeded
        if not RL_DISABLED and getattr(limiter, "limit", None):
            app.state.limiter = limiter
            app.add_middleware(SlowAPIMiddleware)

            async def _rate_limit_handler(request, exc):  # type: ignore
                return JSONResponse(
                    status_code=429, 
                    content={"detail": "Too many requests"}, 
                    headers={"Retry-After": "60"}
                )
            app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)  # type: ignore
    except Exception:  # pragma: no cover
        pass
