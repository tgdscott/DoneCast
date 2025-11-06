"""Routes and static file configuration for the FastAPI application."""
from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi.responses import JSONResponse, FileResponse, Response
from starlette.staticfiles import StaticFiles

if TYPE_CHECKING:
    from fastapi import FastAPI, Request


def attach_routes(app: FastAPI) -> None:
    """Attach all routers and configure health check endpoints.
    
    Args:
        app: FastAPI application instance
    """
    from api.core.logging import get_logger
    from api.routing import attach_routers
    from api.core.database import engine
    from api.core.config import settings
    from urllib.parse import urlparse
    
    log = get_logger("api.config.routes")
    
    # --- Attach Routers ---
    try:
        availability = attach_routers(app)
    except Exception as e:
        log.exception("attach_routers threw an exception: %s", e)
        availability = {}

    def _ensure_users_route_present() -> None:
        # Never crash Cloud Run on missing router; install a minimal 401 fallback so the app can bind PORT.
        paths = {getattr(r, "path", None) for r in app.routes if getattr(r, "path", None)}
        has_users_me = ("/users/me" in paths) or ("/api/users/me" in paths)
        if not has_users_me:
            log.error("Users router not detected at startup; installing fallback /api/users/me -> 401")
            @app.get("/api/users/me")
            async def __fallback_users_me():
                return JSONResponse(status_code=401, content={"detail": "Unauthorized"})

    # If attach_routers reported availability, heed it; otherwise inspect routes.
    if not availability.get("users", False):
        _ensure_users_route_present()

    # --- Health Check Endpoints ---
    @app.get("/api/health")
    def api_health_alias():
        return {"status": "ok"}

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.get("/readyz")
    def readyz():
        try:
            with engine.connect() as conn:
                conn.exec_driver_sql("SELECT 1")
            return {"ok": True}
        except Exception as e:
            return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})
    
    # --- Global CORS Preflight Handler ---
    # Global preflight handler to satisfy browser CORS checks on any path and
    # defensively apply CORS headers even if Starlette's CORSMiddleware misses
    # an edge-case (e.g. complex job_id paths, proxies stripping headers, etc.).
    @app.options("/{path:path}")
    def cors_preflight_handler(path: str, request: Request):  # type: ignore[override]
        origin = request.headers.get("origin") or ""
        requested_headers = request.headers.get("Access-Control-Request-Headers") or request.headers.get("access-control-request-headers")

        # Build a permissive (but restricted to our allowlist / known suffixes) selection.
        allowed_list = settings.cors_allowed_origin_list
        chosen = None
        if origin:
            o = origin.rstrip('/')
            if o in allowed_list:
                chosen = o
            else:
                # Suffix fallback for apex / subdomain variants we trust.
                try:
                    parsed = urlparse(o)
                    host = (parsed.hostname or "").lower()
                    if host:
                        for suffix in ("podcastplusplus.com", "getpodcastplus.com"):
                            if host == suffix or host.endswith(f".{suffix}"):
                                chosen = f"{parsed.scheme}://{parsed.netloc}"
                                break
                except Exception:  # pragma: no cover - defensive
                    chosen = None

        resp = Response(status_code=204)
        if chosen:
            resp.headers['Access-Control-Allow-Origin'] = chosen
            resp.headers.setdefault('Access-Control-Allow-Credentials', 'true')
            # Make sure caching layers vary on Origin so we don't leak headers
            vary_existing = resp.headers.get('Vary')
            vary_vals = [] if not vary_existing else [v.strip() for v in vary_existing.split(',') if v.strip()]
            for v in ("Origin", "Referer"):
                if v not in vary_vals:
                    vary_vals.append(v)
            if vary_vals:
                resp.headers['Vary'] = ", ".join(vary_vals)

        resp.headers.setdefault("Access-Control-Allow-Methods", "GET,POST,PUT,PATCH,DELETE,OPTIONS")
        if requested_headers:
            resp.headers['Access-Control-Allow-Headers'] = requested_headers
        else:
            resp.headers.setdefault("Access-Control-Allow-Headers", "*")
        # Short TTL for preflight cache; browsers will revalidate occasionally.
        resp.headers.setdefault("Access-Control-Max-Age", "600")
        return resp


def configure_static(app: FastAPI) -> None:
    """Configure static file serving and SPA catch-all route.
    
    Args:
        app: FastAPI application instance
    """
    from api.core.paths import FINAL_DIR, MEDIA_DIR, FLUBBER_CTX_DIR, INTERN_CTX_DIR
    
    # --- Static Files ---
    STATIC_UI_DIR = Path(os.getenv("STATIC_UI_DIR", "/app/static_ui"))
    app.mount("/static/final",   StaticFiles(directory=str(FINAL_DIR),   check_dir=False), name="final")
    app.mount("/static/media",   StaticFiles(directory=str(MEDIA_DIR),   check_dir=False), name="media")
    app.mount("/static/flubber", StaticFiles(directory=str(FLUBBER_CTX_DIR), check_dir=False), name="flubber")
    app.mount("/static/intern",  StaticFiles(directory=str(INTERN_CTX_DIR),  check_dir=False), name="intern")

    # --- SPA Catch-All ---
    @app.get("/{full_path:path}")
    async def spa_catch_all(full_path: str):
        if full_path.startswith(("api/", "static/")):
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
        try:
            candidate = STATIC_UI_DIR / full_path
            if candidate.is_file():
                return FileResponse(candidate)
            index = STATIC_UI_DIR / "index.html"
            if index.exists():
                return FileResponse(index, media_type="text/html")
        except Exception:
            pass
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
