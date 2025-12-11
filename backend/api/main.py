"""FastAPI application factory.

This module provides the create_app() function that creates and configures
the FastAPI application instance. The app.py file uses this to expose the
app instance for ASGI servers.
"""
from __future__ import annotations

import os

from fastapi import FastAPI
try:
    from starlette.middleware.proxy_headers import ProxyHeadersMiddleware  # type: ignore
except Exception:  # pragma: no cover - older starlette
    ProxyHeadersMiddleware = None  # type: ignore


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.
    
    This function orchestrates the complete application setup:
    1. Logging and Sentry configuration
    2. FastAPI app instantiation
    3. Proxy headers middleware
    4. Password hash warmup
    5. Application middleware
    6. Rate limiting
    7. Routes and health checks
    8. Static file serving
    9. Startup tasks registration
    
    Returns:
        FastAPI: Configured application instance ready for use by ASGI server.
    """
    from api.core.logging import get_logger

    # Provide a singleton app instance so multiple imports/calls don't
    # re-run full application initialization (which causes duplicated
    # startup logs and handlers). If an app already exists, return it.
    global _APP_SINGLETON  # declared below
    try:
        if _APP_SINGLETON is not None:
            return _APP_SINGLETON
    except NameError:
        _APP_SINGLETON = None

    # Step 1: Configure logging and Sentry
    from api.config.logging import configure_logging, setup_sentry
    configure_logging()
    
    env = os.getenv("APP_ENV") or os.getenv("ENV") or os.getenv("PYTHON_ENV") or "dev"
    setup_sentry(environment=env)
    
    log = get_logger("api.main")
    
    # Step 2: Create FastAPI app
    # CRITICAL: Explicitly set debug=False in production to prevent traceback leaks
    is_dev = env.lower() in ("dev", "development", "local", "test", "testing")
    app = FastAPI(title="DoneCast API", debug=is_dev)
    
    # Step 3: Add proxy headers middleware early
    if ProxyHeadersMiddleware is not None:
        # Use proxy headers if available so request.url_for reflects the external host/scheme
        app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=["*"])
    
    # Step 4: Pre-warm password hashing so first signup isn't slow
    try:
        from api.core.security import get_password_hash
        _ = get_password_hash("__warmup__")  # fire once; result discarded
        log.info("[startup] Password hash warmup complete")
    except Exception as _warm_err:  # pragma: no cover
        log.warning("[startup] Password hash warmup skipped: %s", _warm_err)
    
    # Log database connection pool configuration for debugging
    # CRITICAL: Don't access engine.pool during startup - it may try to connect
    # Just log the configuration without touching the actual pool
    try:
        from api.core import database as db_module
        pool_kwargs = db_module._POOL_KWARGS
        log.info(
            "[db-pool] Configuration: pool_size=%d, max_overflow=%d, pool_timeout=%ds, total_capacity=%d",
            pool_kwargs.get("pool_size", 0),
            pool_kwargs.get("max_overflow", 0),
            pool_kwargs.get("pool_timeout", 30),
            pool_kwargs.get("pool_size", 0) + pool_kwargs.get("max_overflow", 0),
        )
    except Exception as _pool_err:  # pragma: no cover
        log.debug("[db-pool] Could not log pool configuration: %s", _pool_err)
    
    # Import db_listeners to register SQLAlchemy event listeners
    import api.db_listeners  # noqa: F401
    
    # Step 5: Configure middleware
    from api.config.middleware import configure_middleware
    from api.core.config import settings
    configure_middleware(app, settings)
    
    # Step 6: Configure rate limiting
    from api.config.rate_limit import configure_rate_limiting
    configure_rate_limiting(app)
    
    # Step 7: Attach routes and health checks
    from api.config.routes import attach_routes
    attach_routes(app)
    
    # Step 8: Configure static file serving
    from api.config.routes import configure_static
    configure_static(app)
    
    # Step 9: Register startup tasks
    from api.config.startup import register_startup
    register_startup(app)
    
    log.info("[startup] Application configured successfully")
    
    # Cache the created app for subsequent imports/calls
    _APP_SINGLETON = app
    return app


# Provide a module-level app for compatibility with tests and legacy imports
app = create_app()


__all__ = ["create_app", "app"]
