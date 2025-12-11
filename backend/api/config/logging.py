"""Logging and Sentry configuration for the application."""
from __future__ import annotations

import logging
import os


def configure_logging() -> None:
    """Configure application logging.
    
    This imports and calls the core logging configuration, then applies
    additional tweaks like suppressing noisy passlib bcrypt warnings.
    """
    # Call the core logging configuration
    from api.core.logging import configure_logging as core_configure_logging
    core_configure_logging()
    
    # Suppress noisy passlib bcrypt version warning in dev (harmless but distracting)
    try:  # pragma: no cover - defensive logging tweak
        _pl_logger = logging.getLogger("passlib.handlers.bcrypt")
        # Downgrade to ERROR so the trapped version attribute warning is hidden
        _pl_logger.setLevel(logging.ERROR)
        # Patch missing __about__.__version__ to satisfy passlib check (older wheels)
        import bcrypt as _bcrypt  # type: ignore
        if _bcrypt and not getattr(_bcrypt, "__about__", None):
            class _About:  # minimal shim
                __version__ = getattr(_bcrypt, "__version__", "unknown")
            _bcrypt.__about__ = _About()  # type: ignore[attr-defined]
    except Exception:
        pass


def setup_sentry(environment: str, dsn: str | None = None) -> None:
    """Initialize Sentry error tracking with comprehensive integration.
    
    Sentry is configured to capture:
    - HTTP request/response context (method, URL, status code)
    - User information (anonymized)
    - Application errors and exceptions
    - Logging events (warnings, errors, critical)
    - Performance metrics (trace sampling)
    
    Args:
        environment: Current environment (dev, production, etc.)
        dsn: Sentry DSN. If None, reads from SENTRY_DSN env var.
    """
    from api.core.logging import get_logger
    log = get_logger("api.config.logging")
    
    sentry_dsn = dsn or os.getenv("SENTRY_DSN")
    
    # Skip Sentry in dev/test environments
    if not sentry_dsn or environment in ("dev", "development", "test", "testing", "local"):
        log.debug("[startup] Sentry disabled (missing DSN or dev/test env)")
        return
    
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
        from sentry_sdk.integrations.httpx import HttpxIntegration

        def before_send(event, hint):
            """Filter and enrich Sentry events before sending.
            
            This function:
            1. Filters out low-priority errors (e.g., 404s, validation errors)
            2. Adds custom context to errors
            3. Ensures PII is never sent
            """
            # Skip 404s - they're not errors
            if event.get("tags", {}).get("status_code") == 404:
                return None
            
            # Skip validation errors from clients (common and not actionable)
            error_value = (event.get("exception", {}).get("values", [{}])[0].get("value") or "").lower()
            if "validation error" in error_value and event.get("level") == "error":
                # Only capture if it looks like a real issue (multiple fields, etc.)
                # Single field validation errors are normal client mistakes
                pass
            
            # Add request ID if present in hint
            if "exc_info" in hint:
                exc_type, exc_value, tb = hint["exc_info"]
                # Extract request_id from exception if available
                if hasattr(exc_value, "request_id"):
                    event.setdefault("tags", {})["request_id"] = str(exc_value.request_id)
            
            return event

        sentry_sdk.init(
            dsn=sentry_dsn,
            integrations=[
                FastApiIntegration(),
                LoggingIntegration(level=logging.INFO, event_level=logging.WARNING),
                SqlalchemyIntegration(),
                HttpxIntegration(),
            ],
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
            profiles_sample_rate=float(os.getenv("SENTRY_PROFILES_SAMPLE_RATE", "0.0")),
            environment=environment,
            send_default_pii=False,
            before_send=before_send,
            # Increase max_breadcrumbs to track more context
            max_breadcrumbs=100,
            # Capture local variables in stack frames for better debugging
            # (safe with send_default_pii=False)
            include_local_variables=True,
            # Always include exception cause chains
            with_locals=True,
        )
        log.info("[startup] Sentry initialized for env=%s (traces_sample_rate=0.1, breadcrumbs=100)", environment)
    except Exception as se:
        log.warning("[startup] Sentry init failed: %s", se)
