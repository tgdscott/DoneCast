"""Tasks router providing /api/tasks/transcribe for dev + prod.

Historically this endpoint was inlined in app.py backups. Some code (media
upload pipeline) enqueues a task to POST /api/tasks/transcribe with JSON
{"filename": <stored_name>} in dev mode via the synchronous tasks client.

If the route is missing (regression) the dev tasks client will hit the Vite
dev server (when APP_BASE_URL points to :5173), proxy fails (backend down) or
returns HTML, leading to confusing timeouts / body parse errors. Restoring a
dedicated router keeps concerns separated and ensures attach_routers() always
mounts it early.
"""
from __future__ import annotations

import os
import logging
from fastapi import APIRouter, HTTPException, Header, Request
from pydantic import BaseModel

from api.services.transcription import transcribe_media_file  # type: ignore

log = logging.getLogger("tasks.transcribe")

router = APIRouter(prefix="/api/tasks", tags=["tasks"])  # explicit /api prefix

_TASKS_AUTH = os.getenv("TASKS_AUTH", "a-secure-local-secret")
_IS_DEV = (os.getenv("APP_ENV") or os.getenv("ENV") or os.getenv("PYTHON_ENV") or "dev").lower().startswith("dev")


class TranscribeIn(BaseModel):
    filename: str


@router.post("/transcribe")
async def transcribe_endpoint(payload: TranscribeIn, request: Request, x_tasks_auth: str | None = Header(default=None)):
    """Fire a synchronous transcription attempt.

    In dev we allow the default secret; in non‑dev envs we require explicit
    header match. Returns a lightweight status object (does *not* stream
    transcription results) to keep request size small.
    """
    if not _IS_DEV:
        if not x_tasks_auth or x_tasks_auth != _TASKS_AUTH:
            raise HTTPException(status_code=401, detail="unauthorized")

    filename = payload.filename.strip()
    if not filename:
        raise HTTPException(status_code=400, detail="filename required")

    log.info("event=tasks.transcribe.start filename=%s request_id=%s", filename, request.headers.get("x-request-id"))
    try:
        # This call may block for a while; in future we could offload to a thread pool.
        transcribe_media_file(filename)
        log.info("event=tasks.transcribe.done filename=%s", filename)
        return {"started": True}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="file not found")
    except Exception as e:  # pragma: no cover - defensive
        log.exception("event=tasks.transcribe.error filename=%s err=%s", filename, e)
        raise HTTPException(status_code=500, detail="transcription-start-failed")

__all__ = ["router"]
