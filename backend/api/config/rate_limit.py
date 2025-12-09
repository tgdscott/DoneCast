"""Rate limiting configuration for the FastAPI application."""
from __future__ import annotations

import os
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

    # Prefer slowapi-based limits if configured
    try:
        from slowapi.middleware import SlowAPIMiddleware
        from slowapi.errors import RateLimitExceeded
        from api.core.cors import add_cors_headers_to_response
        if not RL_DISABLED and getattr(limiter, "limit", None):
            app.state.limiter = limiter
            app.add_middleware(SlowAPIMiddleware)

            async def _rate_limit_handler(request, exc):  # type: ignore
                response = JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests"},
                    headers={"Retry-After": "60"}
                )
                return add_cors_headers_to_response(response, request)

            app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)  # type: ignore
    except Exception:  # pragma: no cover
        pass

    # Add global fallback middleware (Redis-backed, IP-based) if limits are enabled
    if not RL_DISABLED:
        try:
            from api.core.rate_limiter import RateLimitingMiddleware

            limit = int(os.getenv("RATE_LIMIT_MIDDLEWARE_LIMIT", "100"))
            window = int(os.getenv("RATE_LIMIT_MIDDLEWARE_WINDOW", "60"))

            app.add_middleware(
                RateLimitingMiddleware,
                limit=limit,
                window=window,
            )
        except Exception:  # pragma: no cover
            pass
