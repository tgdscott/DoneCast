"""CORS header utility functions for exception handlers and other edge cases.

This module provides utilities to add CORS headers to responses that bypass
the normal CORS middleware (e.g., exception handlers).
"""
from __future__ import annotations

from urllib.parse import urlparse
from fastapi import Request
from fastapi.responses import JSONResponse

from api.core.config import settings


def add_cors_headers_to_response(response: JSONResponse, request: Request) -> JSONResponse:
    """Add CORS headers to a response, matching the logic from SecurityHeadersMiddleware.
    
    This is needed because exception handlers and some other edge cases bypass the 
    CORS middleware, so we need to manually add CORS headers to these responses.
    
    Args:
        response: The JSONResponse to add CORS headers to
        request: The incoming request to extract the origin from
        
    Returns:
        The response with CORS headers added (if origin is allowed)
    """
    origin = request.headers.get('origin')
    if not origin:
        # Try to derive from Referer header as fallback
        ref = request.headers.get('referer') or request.headers.get('referrer')
        if ref:
            try:
                parsed = urlparse(ref)
                if parsed.scheme and parsed.netloc:
                    origin = f"{parsed.scheme}://{parsed.netloc}"
            except Exception:
                pass
    
    if origin:
        # Check if origin is in allowed list
        allowed_origins = settings.cors_allowed_origin_list
        origin_clean = origin.rstrip('/')
        
        chosen_origin = None
        if origin_clean in allowed_origins:
            chosen_origin = origin_clean
        else:
            # Check if it matches our trusted domain suffixes
            try:
                parsed = urlparse(origin_clean)
                host = (parsed.hostname or "").lower()
                if host:
                    for suffix in ("podcastplusplus.com", "getpodcastplus.com"):
                        if host == suffix or host.endswith(f".{suffix}"):
                            chosen_origin = f"{parsed.scheme}://{parsed.netloc}"
                            break
            except Exception:
                pass
        
        if chosen_origin:
            response.headers['Access-Control-Allow-Origin'] = chosen_origin
            response.headers['Access-Control-Allow-Credentials'] = 'true'
            # Add Vary header to prevent caching issues
            vary_existing = response.headers.get('Vary', '')
            vary_values = [v.strip() for v in vary_existing.split(',') if v.strip()] if vary_existing else []
            for v in ("Origin", "Referer"):
                if v not in vary_values:
                    vary_values.append(v)
            if vary_values:
                response.headers['Vary'] = ", ".join(vary_values)
    
    return response

