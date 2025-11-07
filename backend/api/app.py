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

# Create the application instance with error handling
try:
    from api.main import create_app
    from api.startup_tasks import _compute_pt_expiry  # re-export for backwards compatibility
    
    app = create_app()
    logging.getLogger("api.app").info("[startup] Application created successfully")
except Exception as e:
    # If app creation fails, log the error but still create a minimal app
    # so uvicorn can start and we can see the error in logs
    logging.getLogger("api.app").critical(
        "[startup] Failed to create application: %s", e, exc_info=True
    )
    from fastapi import FastAPI
    app = FastAPI(title="Podcast Pro Plus API (Error Mode)")
    
    @app.get("/healthz")
    def health_error():
        return {"status": "error", "message": f"Startup failed: {str(e)}"}
    
    @app.get("/api/health")
    def api_health_error():
        return {"status": "error", "message": f"Startup failed: {str(e)}"}

__all__ = ["app", "_compute_pt_expiry"]

