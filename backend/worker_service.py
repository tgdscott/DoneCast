"""Dedicated worker service for long-running background tasks.

This service runs as a separate Cloud Run deployment that:
1. Receives task requests via HTTP (from Cloud Tasks)
2. Executes them synchronously in the request handler
3. Returns only after task completion
4. Has extended timeout configured (60 minutes vs 5 minutes for API)

This architecture ensures:
- Tasks complete even if API service restarts
- API service stays responsive (no CPU blocking from FFmpeg)
- Proper resource isolation (workers can scale independently)
- Clean separation of concerns
"""
from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any, Dict

# Configure logging FIRST before any other imports
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s %(name)s: %(message)s',
    stream=sys.stdout,
    force=True  # Override any existing config
)
log = logging.getLogger("worker")

# Import FastAPI - this is lightweight and fast
from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, ValidationError
from starlette.requests import ClientDisconnect

log.info("event=worker.init.start")

app = FastAPI(
    title="Podcast Plus Plus - Worker Service",
    version="1.0.0",
    docs_url=None,  # Disable docs for faster startup
    redoc_url=None,  # Disable redoc for faster startup
)

_TASKS_AUTH = os.getenv("TASKS_AUTH", "a-secure-local-secret")
_IS_DEV = (os.getenv("APP_ENV") or os.getenv("ENV") or os.getenv("PYTHON_ENV") or "dev").lower().startswith("dev")

log.info("event=worker.init.config_loaded is_dev=%s", _IS_DEV)

from worker.tasks import create_podcast_episode
from worker.tasks.assembly.chunk_worker import (
    ProcessChunkPayload,
    run_chunk_processing,
    validate_process_chunk_payload,
)

# Track active tasks for monitoring
import psutil
import threading
from datetime import datetime

_active_tasks = {}
_task_lock = threading.Lock()

# -------------------- Health Check --------------------

@app.get("/")
async def root():
    """Root endpoint for Cloud Run health checks."""
    return {"status": "healthy", "service": "worker", "version": "1.0.0"}


@app.get("/health")
async def health_check():
    """Simple health check endpoint for Cloud Run."""
    return {"status": "healthy", "service": "worker"}


@app.get("/status")
async def worker_status():
    """Real-time worker status and resource usage - NO AUTH REQUIRED for monitoring."""
    try:
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        cpu_percent = process.cpu_percent(interval=0.1)
        
        # Get system-wide stats
        system_memory = psutil.virtual_memory()
        system_cpu = psutil.cpu_percent(interval=0.1, percpu=False)
        
        with _task_lock:
            active_count = len(_active_tasks)
            tasks_snapshot = {
                task_id: {
                    "episode_id": info.get("episode_id"),
                    "type": info.get("type"),
                    "started_at": info.get("started_at"),
                    "duration_seconds": (datetime.utcnow() - datetime.fromisoformat(info.get("started_at"))).total_seconds() if info.get("started_at") else 0
                }
                for task_id, info in _active_tasks.items()
            }
        
        return {
            "status": "healthy",
            "service": "worker",
            "pid": os.getpid(),
            "active_tasks": active_count,
            "tasks": tasks_snapshot,
            "worker_process": {
                "cpu_percent": round(cpu_percent, 1),
                "memory_mb": round(memory_info.rss / 1024 / 1024, 1),
                "memory_percent": round(process.memory_percent(), 1),
            },
            "system": {
                "cpu_percent": round(system_cpu, 1),
                "memory_used_gb": round(system_memory.used / 1024 / 1024 / 1024, 1),
                "memory_total_gb": round(system_memory.total / 1024 / 1024 / 1024, 1),
                "memory_percent": round(system_memory.percent, 1),
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        log.exception("event=worker.status.error")
        return {"status": "error", "error": str(e)}


# -------------------- Episode Assembly --------------------

class AssembleIn(BaseModel):
    episode_id: str
    template_id: str
    main_content_filename: str
    output_filename: str | None = None
    tts_values: Dict[str, Any] | None = None
    episode_details: Dict[str, Any] | None = None
    user_id: str
    podcast_id: str | None = None
    intents: Dict[str, Any] | None = None


def _validate_assemble_payload(data: Dict[str, Any]) -> AssembleIn:
    try:
        return AssembleIn.model_validate(data)  # type: ignore[attr-defined]
    except AttributeError:  # pragma: no cover
        return AssembleIn.parse_obj(data)  # type: ignore[attr-defined]


@app.post("/api/tasks/assemble")
async def assemble_episode_worker(request: Request, x_tasks_auth: str | None = Header(default=None)):
    """Execute episode assembly synchronously in this worker process.
    
    This runs DIRECTLY in the HTTP request handler - no background threads/processes.
    Cloud Run's 60-minute timeout gives us plenty of time to complete.
    
    Security:
      - In dev, allow default secret
      - In non-dev, require X-Tasks-Auth header
    
    Returns:
      - 200 OK with result on success
      - 500 with error details on failure
    """
    # Authenticate
    if not _IS_DEV:
        if not x_tasks_auth or x_tasks_auth != _TASKS_AUTH:
            log.warning("event=worker.assemble.unauthorized")
            raise HTTPException(status_code=401, detail="unauthorized")

    # Parse request body
    try:
        raw_body = await request.body()
    except ClientDisconnect:
        log.warning("event=worker.assemble.client_disconnect")
        raise HTTPException(status_code=499, detail="client disconnected")
    
    raw_body = (raw_body or b"").strip()
    if not raw_body:
        raise HTTPException(status_code=400, detail="request body required")

    try:
        data = json.loads(raw_body.decode("utf-8", errors="ignore"))
        if not isinstance(data, dict):
            raise ValueError("body must be JSON object")
    except Exception as e:
        log.error("event=worker.assemble.bad_body error=%s", str(e))
        raise HTTPException(status_code=400, detail="invalid JSON body")

    # Validate payload
    try:
        payload = _validate_assemble_payload(data)
    except ValidationError as ve:
        log.error("event=worker.assemble.invalid_payload error=%s", str(ve))
        raise HTTPException(status_code=400, detail=f"invalid payload: {ve}")

    # Execute assembly SYNCHRONOUSLY in this request
    log.info("event=worker.assemble.start episode_id=%s pid=%s", payload.episode_id, os.getpid())

    # Track task for monitoring
    task_id = f"assemble-{payload.episode_id}"
    with _task_lock:
        _active_tasks[task_id] = {
            "episode_id": payload.episode_id,
            "type": "assembly",
            "started_at": datetime.utcnow().isoformat()
        }

    try:
        # Import here to avoid loading heavy dependencies on startup
        
        result = create_podcast_episode(
            episode_id=payload.episode_id,
            template_id=payload.template_id,
            main_content_filename=payload.main_content_filename,
            output_filename=payload.output_filename or "",
            tts_values=payload.tts_values or {},
            episode_details=payload.episode_details or {},
            user_id=payload.user_id,
            podcast_id=payload.podcast_id or "",
            intents=payload.intents or None,
        )
        
        log.info("event=worker.assemble.done episode_id=%s result=%s", payload.episode_id, result)
        return {"ok": True, "status": "completed", "episode_id": payload.episode_id, "result": result}
        
    except Exception as exc:
        log.exception("event=worker.assemble.error episode_id=%s", payload.episode_id)
        # Return 500 with error details (Cloud Tasks will retry on 5xx)
        raise HTTPException(
            status_code=500,
            detail=f"Assembly failed: {str(exc)}"
        )
    finally:
        # Remove from active tasks
        with _task_lock:
            _active_tasks.pop(task_id, None)


# -------------------- Chunk Processing --------------------

@app.post("/api/tasks/process-chunk")
async def process_chunk_worker(request: Request, x_tasks_auth: str | None = Header(default=None)):
    """Process a single chunk synchronously within the worker service."""

    if not _IS_DEV:
        if not x_tasks_auth or x_tasks_auth != _TASKS_AUTH:
            log.warning("event=worker.chunk.unauthorized")
            raise HTTPException(status_code=401, detail="unauthorized")

    try:
        raw_body = await request.body()
    except ClientDisconnect:
        log.warning("event=worker.chunk.client_disconnect")
        raise HTTPException(status_code=499, detail="client disconnected")

    raw_body = (raw_body or b"").strip()
    if not raw_body:
        raise HTTPException(status_code=400, detail="request body required")

    try:
        data = json.loads(raw_body.decode("utf-8", errors="ignore"))
        if not isinstance(data, dict):
            raise ValueError("body must be JSON object")
    except Exception as exc:
        log.error("event=worker.chunk.bad_body error=%s", exc)
        raise HTTPException(status_code=400, detail="invalid JSON body")

    try:
        payload: ProcessChunkPayload = validate_process_chunk_payload(data)
    except ValidationError as ve:
        log.error("event=worker.chunk.invalid_payload error=%s", ve)
        raise HTTPException(status_code=400, detail=f"invalid payload: {ve}")

    log.info(
        "event=worker.chunk.start episode_id=%s chunk_id=%s pid=%s",
        payload.episode_id,
        payload.chunk_id,
        os.getpid(),
    )

    # Track task for monitoring
    task_id = f"chunk-{payload.chunk_id}"
    with _task_lock:
        _active_tasks[task_id] = {
            "episode_id": payload.episode_id,
            "chunk_id": payload.chunk_id,
            "type": "chunk_processing",
            "started_at": datetime.utcnow().isoformat()
        }

    try:
        run_chunk_processing(payload)
    except Exception as exc:
        log.exception(
            "event=worker.chunk.error episode_id=%s chunk_id=%s",
            payload.episode_id,
            payload.chunk_id,
        )
        raise HTTPException(status_code=500, detail=f"Chunk processing failed: {exc}")

    log.info(
        "event=worker.chunk.done episode_id=%s chunk_id=%s",
        payload.episode_id,
        payload.chunk_id,
    )
    
    # Remove from active tasks
    with _task_lock:
        _active_tasks.pop(task_id, None)
    
    return {
        "ok": True,
        "status": "completed",
        "chunk_id": payload.chunk_id,
        "episode_id": payload.episode_id,
    }


# -------------------- Startup --------------------

@app.on_event("startup")
async def startup_event():
    """Run minimal initialization - heavy imports deferred to request time."""
    log.info("event=worker.startup pid=%s port=%s", os.getpid(), os.getenv("PORT", "8080"))
    
    # Don't import heavy modules here - it slows down startup
    # Just verify the port binding worked
    log.info("event=worker.ready service=healthy")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    log.info("event=worker.main.start port=%s", port)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
