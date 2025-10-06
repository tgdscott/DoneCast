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

import asyncio
import json
import logging
import os
from typing import Any, Dict
from urllib.parse import parse_qsl

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ValidationError
from starlette.requests import ClientDisconnect

from api.core.paths import MEDIA_DIR
from api.services.transcription import transcribe_media_file  # type: ignore

log = logging.getLogger("tasks.transcribe")

router = APIRouter(prefix="/api/tasks", tags=["tasks"])  # explicit /api prefix

_TASKS_AUTH = os.getenv("TASKS_AUTH", "a-secure-local-secret")
_IS_DEV = (os.getenv("APP_ENV") or os.getenv("ENV") or os.getenv("PYTHON_ENV") or "dev").lower().startswith("dev")


class TranscribeIn(BaseModel):
    filename: str


def _validate_payload(data: Dict[str, Any]) -> TranscribeIn:
    """Support both Pydantic v1 and v2 validation entrypoints."""
    try:
        return TranscribeIn.model_validate(data)  # type: ignore[attr-defined]
    except AttributeError:  # pragma: no cover - pydantic v1 fallback
        return TranscribeIn.parse_obj(data)  # type: ignore[attr-defined]


async def _dispatch_transcription(filename: str, request_id: str | None, *, suppress_errors: bool) -> None:
    """Execute transcription in a worker thread, optionally suppressing exceptions."""
    loop = asyncio.get_running_loop()
    log.info("event=tasks.transcribe.start filename=%s request_id=%s", filename, request_id)
    try:
        await loop.run_in_executor(None, transcribe_media_file, filename)
        log.info("event=tasks.transcribe.done filename=%s request_id=%s", filename, request_id)
    except FileNotFoundError as err:
        log.warning("event=tasks.transcribe.not_found filename=%s request_id=%s", filename, request_id)
        if not suppress_errors:
            raise err
    except Exception as exc:  # pragma: no cover - defensive
        log.exception("event=tasks.transcribe.error filename=%s err=%s", filename, exc)
        if not suppress_errors:
            raise exc


def _ensure_local_media_present(filename: str) -> None:
    """In dev, uploaded files live under MEDIA_DIR; fail fast if missing."""
    if filename.startswith("gs://"):
        return
    candidate = MEDIA_DIR / filename
    if not candidate.exists():
        raise HTTPException(status_code=404, detail="file not found")


@router.post("/transcribe")
async def transcribe_endpoint(request: Request, x_tasks_auth: str | None = Header(default=None)):
    """Fire a transcription attempt.

    In dev we allow the default secret; in non-dev envs we require explicit
    header match. Returns a lightweight status object (does *not* stream
    transcription results) to keep request size small.
    """
    if not _IS_DEV:
        if not x_tasks_auth or x_tasks_auth != _TASKS_AUTH:
            raise HTTPException(status_code=401, detail="unauthorized")

    try:
        raw_body = await request.body()
    except ClientDisconnect:
        log.warning("event=tasks.transcribe.client_disconnect request_id=%s", request.headers.get("x-request-id"))
        raise HTTPException(status_code=499, detail="client disconnected before body was read")

    raw_body = raw_body.strip()
    if not raw_body:
        raise HTTPException(status_code=400, detail="request body required")

    payload_data: Dict[str, Any] | None = None
    try:
        parsed = json.loads(raw_body)
        if isinstance(parsed, dict):
            payload_data = parsed
    except json.JSONDecodeError:
        pass

    if payload_data is None:
        try:
            decoded = raw_body.decode("utf-8", errors="ignore")
            payload_data = {k: v for k, v in parse_qsl(decoded) if k}
        except Exception:
            payload_data = None

    if not payload_data:
        preview = raw_body[:128]
        log.warning(
            "event=tasks.transcribe.bad_body detail=unparsable body_preview=%r content_type=%s request_id=%s",
            preview,
            request.headers.get("content-type"),
            request.headers.get("x-request-id"),
        )
        raise HTTPException(status_code=400, detail="invalid body; expected JSON payload with 'filename'")

    try:
        payload = _validate_payload(payload_data)
    except ValidationError:
        raise HTTPException(status_code=400, detail="filename required")

    filename = (payload.filename or "").strip()
    if not filename:
        raise HTTPException(status_code=400, detail="filename required")

    request_id = request.headers.get("x-request-id")

    if _IS_DEV:
        _ensure_local_media_present(filename)
        asyncio.create_task(_dispatch_transcription(filename, request_id, suppress_errors=True))
        return {"started": True, "async": True}

    try:
        await _dispatch_transcription(filename, request_id, suppress_errors=False)
        return {"started": True}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="file not found")
    except Exception:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail="transcription-start-failed")


__all__ = ["router"]

# -------------------- Assemble Episode (Cloud Tasks) --------------------

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


@router.post("/assemble")
async def assemble_episode_task(request: Request, x_tasks_auth: str | None = Header(default=None)):
    """Run episode assembly via Cloud Tasks (or any HTTP task runner).

    Security:
      - In dev, allow default secret.
      - In non-dev, require X-Tasks-Auth to match TASKS_AUTH env var.

    Behavior:
      - Process ASYNCHRONOUSLY in a background thread to avoid HTTP timeout
      - Returns immediately with 202 Accepted
      - The underlying function is the same implementation used by Celery tasks.
    """
    if not _IS_DEV:
        if not x_tasks_auth or x_tasks_auth != _TASKS_AUTH:
            raise HTTPException(status_code=401, detail="unauthorized")

    try:
        raw_body = await request.body()
    except ClientDisconnect:
        raise HTTPException(status_code=499, detail="client disconnected")
    raw_body = (raw_body or b"").strip()
    if not raw_body:
        raise HTTPException(status_code=400, detail="request body required")

    try:
        data = json.loads(raw_body.decode("utf-8", errors="ignore"))
        if not isinstance(data, dict):
            raise ValueError
    except Exception:
        raise HTTPException(status_code=400, detail="invalid JSON body")

    try:
        payload = _validate_assemble_payload(data)
    except ValidationError as ve:
        raise HTTPException(status_code=400, detail=f"invalid payload: {ve}")

    # Execute asynchronously in separate PROCESS (not thread) to prevent GIL blocking
    # Threading doesn't work for CPU-intensive tasks in Python - it blocks the event loop
    def _run_assembly():
        try:
            # Re-import in child process (multiprocessing requires this)
            import sys
            import logging
            from worker.tasks import create_podcast_episode
            
            # Configure logging in child process
            logging.basicConfig(
                level=logging.INFO,
                format='[%(asctime)s] %(levelname)s %(name)s: %(message)s',
                stream=sys.stdout
            )
            log = logging.getLogger("tasks.assemble.worker")
            
            log.info("event=tasks.assemble.start episode_id=%s pid=%s", payload.episode_id, os.getpid())
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
            log.info("event=tasks.assemble.done episode_id=%s result=%s", payload.episode_id, result)
        except Exception as exc:  # pragma: no cover - defensive
            import logging
            log = logging.getLogger("tasks.assemble.worker")
            log.exception("event=tasks.assemble.error episode_id=%s err=%s", payload.episode_id, exc)

    import multiprocessing
    process = multiprocessing.Process(
        target=_run_assembly,
        name=f"assemble-{payload.episode_id}",
        daemon=True,
    )
    process.start()
    log.info("event=tasks.assemble.dispatched episode_id=%s pid=%s", payload.episode_id, process.pid)
    
    # Return immediately with 202 Accepted
    return {"ok": True, "status": "processing", "episode_id": payload.episode_id}

