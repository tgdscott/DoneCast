# api/middleware/security_headers.py
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
import os
from typing import List
import re
import logging

from ..core.config import settings
from urllib.parse import urlparse

logger = logging.getLogger("security_headers")

TRUSTED_CORS_SUFFIXES = ("podcastplusplus.com", "getpodcastplus.com")

def _normalize_origin(raw: str | None) -> str:
    """Return a canonical origin string (scheme://host[:port]) for comparisons."""
    if not raw:
        return ""
    candidate = raw.strip()
    if not candidate:
        return ""
    candidate = candidate.rstrip("/")
    try:
        parsed = urlparse(candidate)
        if parsed.scheme and parsed.netloc:
            scheme = parsed.scheme.lower()
            host = parsed.netloc.lower()
            return f"{scheme}://{host}"
    except Exception:
        pass
    return candidate.lower()

def _select_origin(effective_origin: str | None, allowed: list[str]) -> str | None:
    """Choose the concrete allowlist entry that matches the request origin."""
    if not effective_origin:
        return None
    normalized = _normalize_origin(effective_origin)
    if not normalized:
        return None
    try:
        mapping = {_normalize_origin(o): o for o in allowed if o}
    except Exception:
        mapping = {}
    match = mapping.get(normalized)
    if match:
        return match
    if effective_origin in allowed:
        return effective_origin
    try:
        parsed = urlparse(normalized)
        host = (parsed.hostname or "").lower()
        scheme = parsed.scheme or "https"
        netloc = parsed.netloc or host
        if host:
            for suffix in TRUSTED_CORS_SUFFIXES:
                if host == suffix or host.endswith(f".{suffix}"):
                    return f"{scheme}://{netloc}"
    except Exception:
        pass
    return None


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)

        path = request.url.path

        # Strict default CSP for your app but allow a few trusted external hosts
        # We allow Google Fonts (fonts.googleapis.com, fonts.gstatic.com) and any
        # additional hosts provided via the CSP_EXTRA_HOSTS env var (comma-separated).
        extra_hosts = os.getenv("CSP_EXTRA_HOSTS", "")

        # Parse, sanitize, and dedupe extra hosts from the env var. We must
        # ensure nothing in the env var can inject a stray semicolon or
        # newline that would turn a host into a directive name.
        def _sanitize_hosts(raw: str) -> List[str]:
            parts = [x.strip() for x in raw.split(",") if x.strip()]
            safe: List[str] = []
            for p in parts:
                # Reject hosts containing characters that would break CSP
                if any(c in p for c in [';', '\n', '\r', '"']):
                    continue
                # Only allow common URL characters (scheme, host, port, path)
                if not re.match(r"^[A-Za-z0-9:/.#%?&=\-@_~]+$", p):
                    continue
                safe.append(p)
            # dedupe while preserving order
            return list(dict.fromkeys(safe))

        safe_hosts = _sanitize_hosts(extra_hosts)

        # Build host lists for different directives
        extra_connect = list(safe_hosts)
        extra_style = list(safe_hosts)
        extra_font = list(safe_hosts)
        # Also allow extra hosts for images when configured
        extra_img = list(safe_hosts)

        # Always include google fonts hosts
        if "https://fonts.googleapis.com" not in extra_style:
            extra_style.append("https://fonts.googleapis.com")
        if "https://fonts.gstatic.com" not in extra_font:
            extra_font.append("https://fonts.gstatic.com")

        # Build directive extras as space-prefixed strings (or empty)
        style_extra = (" " + " ".join(extra_style)) if extra_style else ""
        # Ensure we permit secure-scheme connects (https:) for API calls and CDNs
        if "https:" not in extra_connect:
            extra_connect.insert(0, "https:")
        connect_extra = (" " + " ".join(extra_connect)) if extra_connect else ""
        font_extra = (" " + " ".join(extra_font)) if extra_font else ""
        img_extra = (" " + " ".join(extra_img)) if extra_img else ""

        # Compose a well-formed CSP header where hosts are values for their directives
        default_csp = (
            "default-src 'self'; "
            "base-uri 'self'; "
            "frame-ancestors 'none'; "
            f"media-src 'self' blob:; "
            f"img-src 'self' data:{img_extra}; "
            f"style-src 'self' 'unsafe-inline'{style_extra}; "
            "script-src 'self'; "
            f"connect-src 'self'{connect_extra}; "
            f"font-src 'self' data:{font_extra}; "
            "object-src 'none'"
        )

        # Relaxed CSP ONLY for interactive API docs
        docs_csp = (
            "default-src 'self' https://cdn.jsdelivr.net; "
            "base-uri 'self'; "
            "frame-ancestors 'none'; "
            "img-src 'self' data: https://fastapi.tiangolo.com; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "connect-src 'self'; "
            "font-src 'self' data: https://cdn.jsdelivr.net https://fonts.gstatic.com; "
            "object-src 'none'"
        )

        chosen = docs_csp if path.startswith("/docs") or path.startswith("/redoc") else default_csp
        # Emit the header to stdout for Cloud Run logs so we can verify if the
        # app produced a correct header before any external proxy transforms it.
        # Log at debug level so we can inspect the app-produced header in logs
        # when needed without always printing to stdout.
        try:
            logger.debug("[CSP-DEBUG] path=%s csp=%s", path, chosen)
        except Exception:
            pass
        response.headers["Content-Security-Policy"] = chosen

        # Other helpful headers
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        # Ensure CORS responses have explicit origin when credentials are required.
        # Some proxies (or certain browser flows) may omit or strip the Origin header.
        # As a resilient fallback, derive the origin from the Referer header when safe.
        allowed_origins = settings.cors_allowed_origin_list
        origin = request.headers.get('origin')

        effective_origin = origin
        if not effective_origin:
            # Attempt to derive scheme://host[:port] from Referer for credentialed flows
            ref = request.headers.get('referer') or request.headers.get('referrer')
            if ref:
                try:
                    parsed = urlparse(ref)
                    if parsed.scheme and parsed.netloc:
                        effective_origin = f"{parsed.scheme}://{parsed.netloc}"
                except Exception:
                    effective_origin = None

        # Check if CORSMiddleware already set the CORS headers correctly
        existing_acao = response.headers.get('access-control-allow-origin') or response.headers.get('Access-Control-Allow-Origin')
        
        # If CORSMiddleware already handled it, don't interfere
        if existing_acao and existing_acao != '*':
            # CORSMiddleware already set a specific origin, leave it alone
            pass
        else:
            # CORSMiddleware didn't set it or set it to *, try to be more specific
            selected_origin = _select_origin(effective_origin, allowed_origins)
            if not selected_origin and existing_acao:
                selected_origin = existing_acao

            if selected_origin:
                response.headers['Access-Control-Allow-Origin'] = selected_origin
                response.headers.setdefault('Access-Control-Allow-Credentials', 'true')
                existing_vary = response.headers.get('Vary')
                vary_values = [] if not existing_vary else [v.strip() for v in existing_vary.split(',') if v.strip()]
                for v in ("Origin", "Referer"):
                    if v not in vary_values:
                        vary_values.append(v)
                response.headers['Vary'] = ", ".join(vary_values)
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=()")
        # HSTS header expected by tests
        response.headers.setdefault("Strict-Transport-Security", "max-age=15552000; includeSubDomains")

        return response
