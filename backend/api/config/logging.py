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
    """Initialize Sentry error tracking.
    
    Args:
        environment: Current environment (dev, production, etc.)
        dsn: Sentry DSN. If None, reads from SENTRY_DSN env var.
    """
    from api.core.logging import get_logger
    log = get_logger("api.config.logging")
    
    sentry_dsn = dsn or os.getenv("SENTRY_DSN")
    
    # Skip Sentry in dev/test environments
    if not sentry_dsn or environment in ("dev", "development", "test", "testing", "local"):
        log.info("[startup] Sentry disabled (missing DSN or dev/test env)")
        return
    
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration

        sentry_sdk.init(
            dsn=sentry_dsn,
            integrations=[FastApiIntegration(), LoggingIntegration(level=None, event_level=None)],
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.0")),
            profiles_sample_rate=float(os.getenv("SENTRY_PROFILES_SAMPLE_RATE", "0.0")),
            environment=environment,
            send_default_pii=False,
        )
        log.info("[startup] Sentry initialized for env=%s", environment)
    except Exception as se:
        log.warning("[startup] Sentry init failed: %s", se)
