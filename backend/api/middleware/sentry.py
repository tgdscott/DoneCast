"""Middleware to add user and request context to Sentry.

This middleware enriches all errors with:
- Request ID (for tracing)
- User ID (for identifying affected users)
- Authenticated user context (email, name)
- Request path and method (for grouping similar errors)
"""
from __future__ import annotations

import logging
from typing import Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from api.config.sentry_context import set_user_context, set_request_context, add_breadcrumb

log = logging.getLogger("api.middleware.sentry")


class SentryContextMiddleware(BaseHTTPMiddleware):
    """Middleware that adds user and request context to Sentry for all requests.
    
    This ensures that:
    1. Every error is tagged with the request ID (for support tracing)
    2. Every error is linked to the authenticated user (if available)
    3. Request context (method, path, etc.) is captured
    4. Breadcrumbs track the user's request trail
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process the request and set Sentry context.
        
        Args:
            request: FastAPI request
            call_next: Next middleware/handler
            
        Returns:
            Response from the handler
        """
        try:
            # Extract request ID and user info
            request_id = getattr(request.state, "request_id", None)
            if not request_id:
                request_id = request.headers.get("x-request-id", "unknown")
            
            # Try to get authenticated user from request.state
            user_id = None
            user_email = None
            user_name = None
            
            if hasattr(request.state, "user"):
                user = request.state.user
                if user:
                    user_id = str(getattr(user, "id", None))
                    user_email = getattr(user, "email", None)
                    user_name = getattr(user, "first_name", None)
                    
                    # Set user context in Sentry
                    if user_id:
                        set_user_context(user_id, user_email, user_name)
            elif hasattr(request.state, "user_id"):
                user_id = request.state.user_id
                if user_id:
                    set_user_context(str(user_id))
            
            # Set request context in Sentry
            set_request_context(request)
            
            # Add breadcrumb for the request
            add_breadcrumb(
                message=f"{request.method} {request.url.path}",
                category="http.request",
                level="info",
                data={
                    "method": request.method,
                    "path": request.url.path,
                    "request_id": str(request_id),
                    "user_id": user_id,
                }
            )
            
        except Exception as e:
            log.debug("[sentry] Failed to set request context: %s", e)
        
        # Process the request
        try:
            response = await call_next(request)
        except Exception as e:
            # Log the error and add breadcrumb
            add_breadcrumb(
                message=f"Request failed: {type(e).__name__}",
                category="http.error",
                level="error",
                data={
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                }
            )
            # Let the exception handler deal with it
            raise
        
        # Add breadcrumb for successful response
        try:
            status = response.status_code
            add_breadcrumb(
                message=f"{request.method} {request.url.path} -> {status}",
                category="http.response",
                level="info" if status < 400 else "warning",
                data={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": status,
                }
            )
        except Exception as e:
            log.debug("[sentry] Failed to add response breadcrumb: %s", e)
        
        return response
