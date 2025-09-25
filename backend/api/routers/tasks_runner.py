# api/routers/tasks_runner.py
from __future__ import annotations

import os
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.core.paths import MEDIA_DIR
from api.core.logging import get_logger

log = get_logger("tasks")
router = APIRouter(prefix="/internal/tasks", tags=["internal:tasks"])

_TASKS_AUTH = os.getenv("TASKS_AUTH", "")


def _require_task(request: Request):
    hdr = request.headers.get("x-tasks-auth", "")
    if not _TASKS_AUTH or hdr != _TASKS_AUTH:
        raise HTTPException(status_code=401, detail="unauthorized task")


class TranscribePayload(BaseModel):
    filename: str
    user_id: str | None = None


@router.post("/transcribe")
async def run_transcribe(request: Request, payload: TranscribePayload):
    _require_task(request)
    try:
        # Locate file (uploaded earlier to MEDIA_DIR)
        src = MEDIA_DIR / payload.filename
        if not src.exists():
            raise HTTPException(status_code=404, detail="file not found")

        # Call your existing transcription pipeline.
        # If you already have a function, import and call it here.
        # Example (adjust to your actual module):
        from api.services.transcription import start_transcription  # <- you own this
        job_id = await start_transcription(str(src))  # can be sync; make it awaitable if needed

        return JSONResponse({"ok": True, "job_id": job_id})
    except HTTPException:
        raise
    except Exception as e:
        log.exception("transcribe failed: %s", e)
        raise HTTPException(status_code=500, detail="task failed")
