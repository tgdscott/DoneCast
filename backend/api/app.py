"""FastAPI application entrypoint.

This module imports the application factory from main.py and creates the app instance
that will be used by ASGI servers (uvicorn, gunicorn, etc.).

Usage:
    uvicorn api.app:app --reload
"""
import os
import sys
import logging

# Configure basic logging FIRST before any imports that might log
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s %(name)s: %(message)s',
    stream=sys.stdout,
    force=True
)

# CRITICAL: Ensure app is always defined, even if imports fail
app = None
_compute_pt_expiry = None

# Create the application instance with error handling
try:
    from api.main import create_app
    from api.startup_tasks import _compute_pt_expiry  # re-export for backwards compatibility
    
    app = create_app()
    logging.getLogger("api.app").info("[startup] Application created successfully")
except ImportError as e:
    # If import fails, create a minimal app that shows the import error
    logging.getLogger("api.app").critical(
        "[startup] Import error: %s", e, exc_info=True
    )
    try:
        from fastapi import FastAPI
        app = FastAPI(title="Podcast Pro Plus API (Import Error)")
        
        @app.get("/healthz")
        @app.get("/api/health")
        @app.get("/")
        def health_error():
            return {
                "status": "error", 
                "message": f"Import failed: {str(e)}",
                "error_type": "ImportError"
            }
    except Exception as e2:
        # If even FastAPI import fails, we're in deep trouble
        logging.getLogger("api.app").critical(
            "[startup] Even FastAPI import failed: %s", e2, exc_info=True
        )
        # This should never happen if FastAPI is installed, but if it does,
        # we need to create something that won't crash uvicorn
        # Uvicorn expects an ASGI app, so we create a minimal one
        async def minimal_asgi_app(scope, receive, send):
            if scope["type"] == "http":
                await send({
                    "type": "http.response.start",
                    "status": 500,
                    "headers": [[b"content-type", b"application/json"]],
                })
                await send({
                    "type": "http.response.body",
                    "body": b'{"status":"error","message":"FastAPI not available"}',
                })
        app = minimal_asgi_app
except Exception as e:
    # If app creation fails, log the error but still create a minimal app
    # so uvicorn can start and we can see the error in logs
    error_msg = str(e)
    error_type = type(e).__name__
    logging.getLogger("api.app").critical(
        "[startup] Failed to create application: %s", e, exc_info=True
    )
    try:
        from fastapi import FastAPI
        app = FastAPI(title="Podcast Pro Plus API (Error Mode)")
        
        @app.get("/healthz")
        @app.get("/api/health")
        @app.get("/")
        def health_error():
            return {
                "status": "error", 
                "message": f"Startup failed: {error_msg}",
                "error_type": error_type
            }
    except Exception as e2:
        logging.getLogger("api.app").critical(
            "[startup] Failed to create error app: %s", e2, exc_info=True
        )
        # Last resort: create a minimal ASGI app
        async def minimal_asgi_app(scope, receive, send):
            if scope["type"] == "http":
                await send({
                    "type": "http.response.start",
                    "status": 500,
                    "headers": [[b"content-type", b"application/json"]],
                })
                await send({
                    "type": "http.response.body",
                    "body": b'{"status":"error","message":"App initialization failed"}',
                })
        app = minimal_asgi_app

# Ensure app is never None
if app is None:
    logging.getLogger("api.app").critical("[startup] app is None after initialization!")
    from fastapi import FastAPI
    app = FastAPI(title="Podcast Pro Plus API (Fallback)")
    @app.get("/healthz")
    def health():
        return {"status": "error", "message": "App initialization failed"}

__all__ = ["app"]
if _compute_pt_expiry is not None:
    __all__.append("_compute_pt_expiry")

