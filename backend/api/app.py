"""FastAPI application entrypoint.

This module imports the application factory from main.py and creates the app instance
that will be used by ASGI servers (uvicorn, gunicorn, etc.).

Usage:
    uvicorn api.app:app --reload
"""
from api.main import create_app
from api.startup_tasks import _compute_pt_expiry  # re-export for backwards compatibility

# Create the application instance
app = create_app()

__all__ = ["app", "_compute_pt_expiry"]

