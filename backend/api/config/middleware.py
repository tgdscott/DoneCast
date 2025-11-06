"""Middleware configuration for the FastAPI application."""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request as StarletteRequest

if TYPE_CHECKING:
    from fastapi import FastAPI
    from api.core.config import Settings


def configure_middleware(app: FastAPI, settings: Settings) -> None:
    """Configure all middleware for the application.
    
    Args:
        app: FastAPI application instance
        settings: Application settings
    """
    from api.core.logging import get_logger
    log = get_logger("api.config.middleware")
    
    # Determine environment for session cookie configuration
    env = os.getenv("APP_ENV") or os.getenv("ENV") or os.getenv("PYTHON_ENV") or "dev"
    _is_dev = str(env).lower() in {"dev", "development", "local", "test", "testing"}
    
    # Session middleware
    # In dev/test environments, don't mark the session cookie as Secure and
    # relax SameSite so the cookie is sent on the OAuth redirect back from Google.
    # In prod, keep SameSite=None + Secure (https_only=True) for cross-site flows.
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.SESSION_SECRET_KEY,
        session_cookie="ppp_session",
        max_age=60 * 60 * 24 * 14,
        same_site=("lax" if _is_dev else "none"),
        https_only=(False if _is_dev else True),
    )
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origin_list,
        allow_origin_regex=r"https://(?:[a-z0-9-]+\.)?(?:podcastplusplus\.com|getpodcastplus\.com)",
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
        allow_credentials=True,
    )
    
    # Dev Safety Middleware (Cloud SQL Proxy protection)
    from api.middleware.dev_safety import dev_read_only_middleware
    app.middleware("http")(dev_read_only_middleware)
    
    # Security and Request ID middleware
    from api.middleware.request_id import RequestIDMiddleware
    from api.middleware.security_headers import SecurityHeadersMiddleware
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    
    # Response logging middleware for CORS debugging
    class ResponseLoggingMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: StarletteRequest, call_next):
            try:
                origin = request.headers.get("origin")
                method = request.method
                path = request.url.path
                log.debug("[CORS-DBG] incoming %s %s origin=%s", method, path, origin)
            except Exception:
                pass
            response = await call_next(request)
            try:
                aco = response.headers.get("access-control-allow-origin")
                acc = response.headers.get("access-control-allow-credentials")
                log.debug("[CORS-DBG] response for %s %s: A-C-A-O=%s A-C-A-C=%s request_id=%s",
                          method, path, aco, acc, response.headers.get("x-request-id"))
            except Exception:
                pass
            return response

    app.add_middleware(ResponseLoggingMiddleware)
    
    # Install exception handlers
    from api.exceptions import install_exception_handlers
    install_exception_handlers(app)
