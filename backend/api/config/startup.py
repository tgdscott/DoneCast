"""Startup task configuration for the FastAPI application."""
from __future__ import annotations

import os
import threading
import time as _time
from pathlib import Path as _Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI


def _launch_startup_tasks() -> None:
    """Run additive migrations & housekeeping in background.

    CRITICAL: To meet Cloud Run's 2-second startup requirement, this function launches
    a background thread that runs AFTER the HTTP server is ready. This prevents slow
    database/GCS operations from blocking container health checks.

    Environment controls:
      SKIP_STARTUP_MIGRATIONS=1 -> skip entirely
      BLOCKING_STARTUP_TASKS=1 or STARTUP_TASKS_MODE=sync -> run inline (NOT RECOMMENDED in prod)
    """
    from api.core.logging import get_logger
    from api.startup_tasks import run_startup_tasks
    
    log = get_logger("api.config.startup")
    
    skip = (os.getenv("SKIP_STARTUP_MIGRATIONS") or "").lower() in {"1","true","yes","on"}
    mode = (os.getenv("STARTUP_TASKS_MODE") or "async").lower()
    blocking_flag = (os.getenv("BLOCKING_STARTUP_TASKS") or "").lower() in {"1","true","yes","on"}
    sentinel_path = _Path(os.getenv("STARTUP_SENTINEL_PATH", "/tmp/ppp_startup_done"))
    single = (os.getenv("SINGLE_STARTUP_TASKS") or "1").lower() in {"1","true","yes","on"}
    
    if skip:
        log.warning("[deferred-startup] SKIP_STARTUP_MIGRATIONS=1 -> skipping run_startup_tasks()")
        return
    if single and sentinel_path.exists():
        log.info("[deferred-startup] Sentinel %s exists -> skipping startup tasks", sentinel_path)
        return
    if blocking_flag or mode == "sync":
        log.warning("[deferred-startup] BLOCKING mode enabled - startup will be SLOW (not recommended for Cloud Run)")
        try:
            run_startup_tasks()
            log.info("[deferred-startup] Startup tasks complete (sync)")
            if single:
                try:
                    sentinel_path.write_text(str(int(_time.time())))
                except Exception:
                    pass
        except Exception as e:  # pragma: no cover
            log.exception("[deferred-startup] Startup tasks failed (sync): %s", e)
        return
    
    # Run in background thread with delay to ensure HTTP server is ready first
    def _runner():
        # Wait 5 seconds to let container become healthy before heavy operations
        _time.sleep(5.0)
        start_ts = _time.time()
        try:
            log.info("[deferred-startup] Background startup tasks begin (after 5s delay)")
            run_startup_tasks()
            elapsed = _time.time() - start_ts
            log.info("[deferred-startup] Startup tasks complete in %.2fs", elapsed)
            if single:
                try:
                    sentinel_path.write_text(str(int(_time.time())))
                except Exception:
                    pass
        except Exception as e:  # pragma: no cover
            log.exception("[deferred-startup] Startup tasks failed: %s", e)
    try:
        thread = threading.Thread(target=_runner, name="startup-tasks", daemon=True)
        thread.start()
        log.info("[deferred-startup] Launched background thread (will start after 5s delay)")
    except Exception as e:  # pragma: no cover
        log.exception("[deferred-startup] Could not launch background startup tasks: %s", e)


def register_startup(app: FastAPI) -> None:
    """Register startup event handlers with the FastAPI app.
    
    Args:
        app: FastAPI application instance
    """
    @app.on_event("startup")
    async def _kickoff_background_startup():  # type: ignore
        _launch_startup_tasks()
