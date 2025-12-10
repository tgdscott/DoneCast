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

import json
import logging
import os
from typing import Any, Dict
from urllib.parse import parse_qsl

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ValidationError
from starlette.requests import ClientDisconnect

from api.core.paths import MEDIA_DIR
from api.core.database import get_session
from api.services.episodes.queue_retry import retry_queued_episodes
from worker.tasks.assembly.chunk_worker import (
    ProcessChunkPayload,
    run_chunk_processing,
    validate_process_chunk_payload,
)

log = logging.getLogger("tasks.transcribe")

router = APIRouter(prefix="/api/tasks", tags=["tasks"])  # explicit /api prefix

_TASKS_AUTH = os.getenv("TASKS_AUTH", "a-secure-local-secret")
_IS_DEV = (os.getenv("APP_ENV") or os.getenv("ENV") or os.getenv("PYTHON_ENV") or "dev").lower().startswith("dev")


class TranscribeIn(BaseModel):
    filename: str
    user_id: str | None = None  # Optional: determines which transcription service to use
    guest_ids: list[str] | None = None  # Optional: list of guest IDs for speaker ID


def _validate_payload(data: Dict[str, Any]) -> TranscribeIn:
    """Support both Pydantic v1 and v2 validation entrypoints."""
    try:
        return TranscribeIn.model_validate(data)  # type: ignore[attr-defined]
    except AttributeError:  # pragma: no cover - pydantic v1 fallback
        return TranscribeIn.parse_obj(data)  # type: ignore[attr-defined]


async def _dispatch_transcription(
    filename: str, 
    user_id: str | None,
    request_id: str | None, 
        audio_quality_label: str | None = None
        audio_quality_metrics: dict | None = None
        use_auphonic: bool | None = None
    *, 
    suppress_errors: bool,
    guest_ids: list[str] | None = None
) -> None:
    """Execute transcription in a worker thread, optionally suppressing exceptions."""
    import asyncio
    from api.services.transcription import transcribe_media_file  # type: ignore
    
    loop = asyncio.get_running_loop()
    log.info("event=tasks.transcribe.start filename=%s user_id=%s request_id=%s guest_ids=%s", filename, user_id, request_id, guest_ids)
    try:
        await loop.run_in_executor(None, transcribe_media_file, filename, user_id, guest_ids)
        log.info("event=tasks.transcribe.done filename=%s request_id=%s", filename, request_id)
    except FileNotFoundError as err:
        log.warning("event=tasks.transcribe.not_found filename=%s request_id=%s", filename, request_id)
        
        # Report as bug if user context available
        if user_id:
            try:
                from api.core.database import get_session
                from api.models.user import User
                from api.services.bug_reporter import report_transcription_failure
                from sqlmodel import select
                
                session = next(get_session())
                user = session.exec(select(User).where(User.id == user_id)).first()
                
                if user:
                    report_transcription_failure(
                        session=session,
                        user=user,
                        media_filename=filename,
                        transcription_service="AssemblyAI" if not use_auphonic else "Auphonic",
                        error_message="Audio file not found in storage",
                        request_id=request_id,
                    )
            except Exception as report_err:
                log.warning("Failed to report transcription FileNotFoundError as bug: %s", report_err)
        
        if not suppress_errors:
            raise err
    except Exception as exc:  # pragma: no cover - defensive
        log.exception("event=tasks.transcribe.error filename=%s err=%s", filename, exc)
        
        # Report as bug - ALWAYS report transcription failures
        if user_id:
            try:
                from api.core.database import get_session
                from api.models.user import User
                from api.services.bug_reporter import report_transcription_failure
                from api.services.upload_completion_mailer import send_upload_failure_email
                from sqlmodel import select
                
                session = next(get_session())
                user = session.exec(select(User).where(User.id == user_id)).first()
                
                if user:
                    # Report bug to tracking system
                    report_transcription_failure(
                        session=session,
                        user=user,
                        media_filename=filename,
                        transcription_service="AssemblyAI" if not use_auphonic else "Auphonic",
                        error_message=str(exc),
                        request_id=request_id,
                    )
                    
                    # Send user notification email
                    try:
                        send_upload_failure_email(
                            user=user,
                            filename=filename,
                            error_message="Failed to transcribe your audio. This has been reported to our support team.",
                            error_code="TRANSCRIPTION_FAILED",
                            request_id=request_id,
                        )
                    except Exception as email_err:
                        log.warning("Failed to send transcription failure email: %s", email_err)
            except Exception as report_err:
                log.warning("Failed to report transcription error as bug: %s", report_err)
        
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
    user_id = (payload.user_id or "").strip() or None  # Extract user_id from payload
    guest_ids = payload.guest_ids or None
    
    if not filename:
        raise HTTPException(status_code=400, detail="filename required")

    request_id = request.headers.get("x-request-id")

    if _IS_DEV:
        _ensure_local_media_present(filename)
        import asyncio
        asyncio.create_task(_dispatch_transcription(filename, user_id, request_id, suppress_errors=True, guest_ids=guest_ids))
        return {"started": True, "async": True}

    try:
        await _dispatch_transcription(filename, user_id, request_id, suppress_errors=False, guest_ids=guest_ids)
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
    use_auphonic: bool | None = None


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
            from worker.tasks.assembly.orchestrator import orchestrate_create_podcast_episode
            
            # Configure logging in child process
            logging.basicConfig(
                level=logging.INFO,
                format='[%(asctime)s] %(levelname)s %(name)s: %(message)s',
                stream=sys.stdout
            )
            log = logging.getLogger("tasks.assemble.worker")
            
            log.info("event=tasks.assemble.start episode_id=%s pid=%s", payload.episode_id, os.getpid())
            
            # Extract use_auphonic flag from episode_details if present
            if payload.use_auphonic is None:
                use_auphonic = (payload.episode_details or {}).get('use_auphonic', False)
            else:
                use_auphonic = payload.use_auphonic
            
            result = orchestrate_create_podcast_episode(
                episode_id=payload.episode_id,
                template_id=payload.template_id,
                main_content_filename=payload.main_content_filename,
                output_filename=payload.output_filename or "",
                tts_values=payload.tts_values or {},
                episode_details=payload.episode_details or {},
                user_id=payload.user_id,
                podcast_id=payload.podcast_id or "",
                intents=payload.intents or None,
                skip_charge=False,
                use_auphonic=bool(use_auphonic),
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
        daemon=False,  # Allow process to finish even if parent exits
    )
    process.start()
    log.info("event=tasks.assemble.dispatched episode_id=%s pid=%s", payload.episode_id, process.pid)
    
    # CRITICAL: Wait for assembly to complete before returning
    # If we return immediately, Cloud Run scales down and kills the child process
    # IMPORTANT: Timeout MUST be less than Cloud Tasks dispatchDeadline (1800s)
    # to allow proper retry behavior. Using 1700s to give 100s buffer.
    process.join(timeout=1700)  # 28m20s max (less than 30min Cloud Tasks deadline)
    
    if process.is_alive():
        log.error("event=tasks.assemble.timeout episode_id=%s", payload.episode_id)
        process.terminate()
        process.join(timeout=5)
        return {"ok": False, "status": "timeout", "episode_id": payload.episode_id}
    
    exit_code = process.exitcode
    if exit_code == 0:
        log.info("event=tasks.assemble.success episode_id=%s", payload.episode_id)
        return {"ok": True, "status": "completed", "episode_id": payload.episode_id}
    else:
        log.error("event=tasks.assemble.failed episode_id=%s exit_code=%s", payload.episode_id, exit_code)
        return {"ok": False, "status": "error", "episode_id": payload.episode_id, "exit_code": exit_code}


# -------------------- Process Audio Chunk (Cloud Tasks) --------------------

class ProcessChunkIn(BaseModel):
    """Payload for processing a single audio chunk."""
    episode_id: str
    chunk_id: str
    chunk_index: int
    total_chunks: int = 1  # Default to 1 for backwards compatibility
    gcs_audio_uri: str
    gcs_transcript_uri: str | None = None
    cleanup_options: Dict[str, Any] | None = None
    user_id: str


def _validate_process_chunk_payload(data: Dict[str, Any]) -> ProcessChunkIn:
    try:
        return ProcessChunkIn.model_validate(data)  # type: ignore[attr-defined]
    except AttributeError:  # pragma: no cover
        return ProcessChunkIn.parse_obj(data)  # type: ignore[attr-defined]


def run_chunk_processing(payload_data: Dict[str, Any]) -> None:
    """Execute the chunk-processing worker logic synchronously."""

    try:
        payload = _validate_process_chunk_payload(payload_data)
    except ValidationError as exc:
        worker_log = logging.getLogger("tasks.process_chunk.worker")
        worker_log.error(
            "event=chunk.payload_invalid err=%s payload=%s",
            exc,
            payload_data,
        )
        return

    try:
        import sys
        import tempfile
        from pathlib import Path

        from pydub import AudioSegment

        if not logging.getLogger().handlers:
            logging.basicConfig(
                level=logging.INFO,
                format='[%(asctime)s] %(levelname)s %(name)s: %(message)s',
                stream=sys.stdout,
            )

        worker_log = logging.getLogger("tasks.process_chunk.worker")
        worker_log.info(
            "event=chunk.start episode_id=%s chunk_id=%s pid=%s",
            payload.episode_id,
            payload.chunk_id,
            os.getpid(),
        )

        import infrastructure.gcs as gcs

        with tempfile.TemporaryDirectory(prefix=f"chunk_{payload.chunk_index}_") as tmpdir:
            tmpdir_path = Path(tmpdir)

            worker_log.info("event=chunk.download uri=%s", payload.gcs_audio_uri)
            chunk_audio_path = tmpdir_path / f"chunk_{payload.chunk_index}.wav"

            gcs_uri = payload.gcs_audio_uri
            if gcs_uri.startswith("gs://"):
                parts = gcs_uri[5:].split("/", 1)
                if len(parts) == 2:
                    bucket_name, blob_path = parts
                    audio_bytes = gcs.download_gcs_bytes(bucket_name, blob_path)
                    if audio_bytes:
                        chunk_audio_path.write_bytes(audio_bytes)
                        worker_log.info(
                            "event=chunk.downloaded size=%d",
                            len(audio_bytes),
                        )
                    else:
                        worker_log.error(
                            "event=chunk.download_failed uri=%s",
                            gcs_uri,
                        )
                        return

            transcript_data = None
            if payload.gcs_transcript_uri:
                worker_log.info(
                    "event=chunk.download_transcript uri=%s",
                    payload.gcs_transcript_uri,
                )
                gcs_uri = payload.gcs_transcript_uri
                if gcs_uri.startswith("gs://"):
                    parts = gcs_uri[5:].split("/", 1)
                    if len(parts) == 2:
                        bucket_name, blob_path = parts
                        transcript_bytes = gcs.download_gcs_bytes(
                            bucket_name,
                            blob_path,
                        )
                        if transcript_bytes:
                            transcript_data = json.loads(
                                transcript_bytes.decode("utf-8")
                            )
                            if isinstance(transcript_data, list):
                                word_count = len(transcript_data)
                            elif isinstance(transcript_data, dict):
                                word_count = len(transcript_data.get("words", []))
                            else:
                                word_count = 0
                            worker_log.info(
                                "event=chunk.transcript_downloaded words=%d",
                                word_count,
                            )

            worker_log.info(
                "event=chunk.clean_start chunk_path=%s",
                chunk_audio_path,
            )
            cleanup_opts = payload.cleanup_options or {}

            audio = AudioSegment.from_file(str(chunk_audio_path))
            worker_log.info("event=chunk.loaded duration_ms=%d", len(audio))

            from api.services.audio.cleanup import (
                compress_long_pauses_guarded,
                rebuild_audio_from_words,
            )

            cleaned_audio = audio
            mutable_words = (
                transcript_data
                if isinstance(transcript_data, list)
                else (
                    transcript_data.get("words", [])
                    if transcript_data
                    else []
                )
            )

            if cleanup_opts.get("removeFillers", True) and mutable_words:
                filler_words_list = cleanup_opts.get("fillerWords", []) or []
                filler_words = {
                    str(w).strip().lower()
                    for w in filler_words_list
                    if str(w).strip()
                }
                if filler_words:
                    worker_log.info(
                        "event=chunk.removing_fillers count=%d",
                        len(filler_words),
                    )
                    cleaned_audio, _, _ = rebuild_audio_from_words(
                        audio,
                        mutable_words,
                        filler_words=filler_words,
                        remove_fillers=True,
                        filler_lead_trim_ms=int(
                            cleanup_opts.get("fillerLeadTrimMs", 60)
                        ),
                        log=[],
                    )

            if cleanup_opts.get("removePauses", True):
                worker_log.info("event=chunk.compressing_pauses")
                cleaned_audio = compress_long_pauses_guarded(
                    cleaned_audio,
                    max_pause_s=float(
                        cleanup_opts.get("maxPauseSeconds", 1.5)
                    ),
                    min_target_s=float(
                        cleanup_opts.get("targetPauseSeconds", 0.5)
                    ),
                    ratio=float(
                        cleanup_opts.get("pauseCompressionRatio", 0.4)
                    ),
                    rel_db=16.0,
                    removal_guard_pct=float(
                        cleanup_opts.get("maxPauseRemovalPct", 0.1)
                    ),
                    similarity_guard=float(
                        cleanup_opts.get("pauseSimilarityGuard", 0.85)
                    ),
                    log=[],
                )

            is_last_chunk = payload.chunk_index == payload.total_chunks - 1
            if is_last_chunk and mutable_words:
                last_word_end_ms = 0
                for word in mutable_words:
                    word_end = word.get("end", 0) * 1000
                    if word_end > last_word_end_ms:
                        last_word_end_ms = word_end

                trim_point_ms = int(last_word_end_ms + 500)
                if trim_point_ms < len(cleaned_audio):
                    worker_log.info(
                        "event=chunk.trim_trailing_silence last_word_end=%d trim_point=%d audio_duration=%d",
                        last_word_end_ms,
                        trim_point_ms,
                        len(cleaned_audio),
                    )
                    cleaned_audio = cleaned_audio[:trim_point_ms]

            worker_log.info(
                "event=chunk.cleaned original_ms=%d cleaned_ms=%d",
                len(audio),
                len(cleaned_audio),
            )

            cleaned_audio_path = (
                tmpdir_path / f"chunk_{payload.chunk_index}_cleaned.mp3"
            )
            worker_log.info("event=chunk.export path=%s", cleaned_audio_path)
            cleaned_audio.export(str(cleaned_audio_path), format="mp3")

            cleaned_gcs_path = payload.gcs_audio_uri.replace(
                ".wav",
                "_cleaned.mp3",
            ).replace("gs://ppp-media-us-west1/", "")
            worker_log.info("event=chunk.upload path=%s", cleaned_gcs_path)

            cleaned_bytes = cleaned_audio_path.read_bytes()
            worker_log.info("event=chunk.upload.bytes_read size=%d", len(cleaned_bytes))
            
            # CRITICAL: Chunks MUST be uploaded to GCS, not R2
            # Use GCS directly with force_gcs=True to bypass STORAGE_BACKEND routing
            import infrastructure.gcs as gcs_module
            try:
                cleaned_uri = gcs_module.upload_bytes(
                    "ppp-media-us-west1",
                    cleaned_gcs_path,
                    cleaned_bytes,
                    content_type="audio/mpeg",
                    force_gcs=True,  # Force GCS even if STORAGE_BACKEND=r2
                    allow_fallback=False  # Chunks require GCS - no fallback allowed
                )
                if not cleaned_uri or not cleaned_uri.startswith("gs://"):
                    raise RuntimeError(f"Chunk upload returned invalid URI: {cleaned_uri}")
                worker_log.info("event=chunk.upload.success uri=%s", cleaned_uri)
            except Exception as upload_err:
                worker_log.exception(
                    "event=chunk.upload.failed path=%s err=%s",
                    cleaned_gcs_path,
                    upload_err,
                )
                raise

            worker_log.info(
                "event=chunk.complete episode_id=%s chunk_id=%s cleaned_uri=%s",
                payload.episode_id,
                payload.chunk_id,
                cleaned_uri,
            )
    except Exception as exc:  # pragma: no cover - defensive
        worker_log = logging.getLogger("tasks.process_chunk.worker")
        worker_log.exception(
            "event=chunk.error episode_id=%s chunk_id=%s err=%s",
            payload_data.get("episode_id"),
            payload_data.get("chunk_id"),
            exc,
        )

@router.post("/process-chunk")
async def process_chunk_task(request: Request, x_tasks_auth: str | None = Header(default=None)):
    """Process a single audio chunk via Cloud Tasks.
    
    This endpoint:
    1. Downloads the chunk from GCS
    2. Runs audio cleaning on the chunk
    3. Uploads the cleaned chunk back to GCS
    4. Updates chunk status in episode metadata
    
    Returns immediately with 202 Accepted.
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
        payload: ProcessChunkPayload = validate_process_chunk_payload(data)
    except ValidationError as ve:
        raise HTTPException(status_code=400, detail=f"invalid payload: {ve}")

    log.info("event=chunk.dispatched episode_id=%s chunk_id=%s",
            payload.episode_id, payload.chunk_id)
    
    # Run chunk processing SYNCHRONOUSLY (not multiprocessing.Process)
    # Cloud Run kills orphaned child processes, causing silent failures
    # Blocking the request ensures the process completes
    try:
        run_chunk_processing(payload.model_dump())
        log.info("event=chunk.handler_complete episode_id=%s chunk_id=%s",
                payload.episode_id, payload.chunk_id)
    except Exception as e:
        log.exception("event=chunk.handler_error episode_id=%s chunk_id=%s err=%s",
                     payload.episode_id, payload.chunk_id, e)
        raise HTTPException(status_code=500, detail=f"chunk processing failed: {e}")
    
    return {"ok": True, "status": "completed", "chunk_id": payload.chunk_id}


# ============================================================================
# MAINTENANCE TASKS (Cloud Scheduler endpoints)
# ============================================================================

@router.post("/maintenance/purge-expired-uploads")
async def maintenance_purge_expired_uploads(
    request: Request,
    x_tasks_auth: str | None = Header(default=None)
):
    """Delete expired raw uploads that are no longer referenced.
    
    Triggered by Cloud Scheduler daily at 2:00 AM PT.
    
    For recordings (main_content), enforces 24-hour minimum retention period
    even if used in an episode, giving users time to download a backup.
    """
    if not _IS_DEV:
        # Accept either Cloud Scheduler OIDC token OR legacy TASKS_AUTH header
        auth_header = request.headers.get("Authorization", "")
        has_oidc = auth_header.startswith("Bearer ")
        has_tasks_auth = x_tasks_auth and x_tasks_auth == _TASKS_AUTH
        
        if not (has_oidc or has_tasks_auth):
            raise HTTPException(status_code=401, detail="unauthorized")

    from datetime import datetime, timedelta
    from pathlib import Path
    from sqlmodel import select
    from api.core.database import get_session
    from api.core.paths import MEDIA_DIR
    from api.models.podcast import Episode, MediaCategory, MediaItem, EpisodeStatus
    
    session = next(get_session())
    now = datetime.utcnow()
    removed = 0
    skipped_in_use = 0
    skipped_too_young = 0
    checked = 0

    try:
        query = (
            select(MediaItem)
            .where(MediaItem.category == MediaCategory.main_content)  # type: ignore
            .where(MediaItem.expires_at != None)  # type: ignore
            .where(MediaItem.expires_at <= now)  # type: ignore
            .limit(10_000)
        )
        items = session.exec(query).all()

        episode_query = select(Episode)
        episodes = session.exec(episode_query).all()
        in_use: set[str] = set()
        
        # Only mark files as "in use" if they're referenced by incomplete episodes
        incomplete_statuses = {
            EpisodeStatus.pending,
            EpisodeStatus.processing,
            EpisodeStatus.error,
        }
        
        for ep in episodes:
            ep_status = getattr(ep, "status", None)
            if ep_status not in incomplete_statuses:
                continue
                
            # Episode is incomplete, keep its files
            for name in (
                getattr(ep, "working_audio_name", None),
                getattr(ep, "final_audio_path", None),
            ):
                if not name:
                    continue
                try:
                    in_use.add(Path(str(name)).name)
                except Exception:
                    in_use.add(str(name))
            
            # Check meta_json for main_content_filename
            try:
                meta_str = getattr(ep, "meta_json", None)
                if meta_str:
                    meta = json.loads(meta_str)
                    if isinstance(meta, dict):
                        main_content = meta.get("main_content_filename")
                        if main_content:
                            try:
                                in_use.add(Path(str(main_content)).name)
                            except Exception:
                                in_use.add(str(main_content))
            except Exception:
                pass

        for media_item in items:
            checked += 1
            filename = getattr(media_item, "filename", None)
            if not filename:
                continue
            
            # Enforce 24-hour minimum retention
            created_at = getattr(media_item, "created_at", None)
            if created_at:
                age_hours = (now - created_at).total_seconds() / 3600
                if age_hours < 24:
                    skipped_too_young += 1
                    continue
            
            if filename in in_use:
                skipped_in_use += 1
                continue

            try:
                path = MEDIA_DIR / filename
                if path.exists():
                    try:
                        path.unlink()
                    except Exception:
                        log.warning("[purge] Failed to unlink %s", path, exc_info=True)
                session.delete(media_item)
                removed += 1
            except Exception:
                log.warning("[purge] Failed to delete MediaItem %s", 
                           getattr(media_item, "id", None), exc_info=True)

        if removed:
            session.commit()
    except Exception:
        session.rollback()
        log.warning("[purge] purge_expired_uploads failed", exc_info=True)
        raise HTTPException(status_code=500, detail="maintenance task failed")
    finally:
        session.close()

    log.info("[purge] expired uploads: checked=%s removed=%s skipped_in_use=%s skipped_too_young=%s",
             checked, removed, skipped_in_use, skipped_too_young)
    
    return {
        "ok": True,
        "checked": checked,
        "removed": removed,
        "skipped_in_use": skipped_in_use,
        "skipped_too_young": skipped_too_young
    }


@router.post("/maintenance/purge-episode-mirrors")
async def maintenance_purge_episode_mirrors(
    request: Request,
    x_tasks_auth: str | None = Header(default=None)
):
    """Remove mirrored audio for Spreaker episodes published more than 7 days ago.
    
    Triggered by Cloud Scheduler daily at 2:00 AM PT.
    
    Legacy cleanup for episodes published to Spreaker (before GCS-only architecture).
    """
    if not _IS_DEV:
        # Accept either Cloud Scheduler OIDC token OR legacy TASKS_AUTH header
        auth_header = request.headers.get("Authorization", "")
        has_oidc = auth_header.startswith("Bearer ")
        has_tasks_auth = x_tasks_auth and x_tasks_auth == _TASKS_AUTH
        
        if not (has_oidc or has_tasks_auth):
            raise HTTPException(status_code=401, detail="unauthorized")

    from datetime import datetime, timedelta
    from pathlib import Path
    from sqlmodel import select
    from api.core.database import get_session
    from api.core.paths import FINAL_DIR
    from api.models.podcast import Episode
    from infrastructure.gcs import delete_gcs_blob
    
    session = next(get_session())
    cutoff = datetime.utcnow() - timedelta(days=7)
    checked = 0
    removed_local = 0
    removed_remote = 0

    try:
        episodes = session.exec(
            select(Episode).where(Episode.spreaker_episode_id != None)  # type: ignore
        ).all()

        for episode in episodes:
            try:
                meta = json.loads(getattr(episode, "meta_json", "{}") or "{}")
                if not isinstance(meta, dict):
                    meta = {}
            except Exception:
                meta = {}

            local_basename = meta.get("mirrored_local_basename")
            if not local_basename:
                continue

            publish_at = getattr(episode, "publish_at", None) or getattr(episode, "processed_at", None)
            if not publish_at or publish_at > cutoff:
                continue

            checked += 1
            local_path = (FINAL_DIR / Path(str(local_basename)).name).resolve()
            if local_path.exists():
                try:
                    local_path.unlink()
                    removed_local += 1
                except Exception:
                    log.warning("[purge] failed to delete mirrored audio %s", local_path, exc_info=True)

            # Handle both old format (mirrored_gcs_key) and new format (mirrored_gcs_uri)
            gcs_uri = meta.get("mirrored_gcs_uri")
            if isinstance(gcs_uri, str) and gcs_uri.startswith("gs://"):
                try:
                    bucket_key = gcs_uri[5:]
                    bucket, _, key = bucket_key.partition("/")
                    if bucket and key:
                        delete_gcs_blob(bucket, key)
                        removed_remote += 1
                except Exception:
                    log.warning("[purge] failed to delete mirrored blob %s", gcs_uri, exc_info=True)

        session.commit()
    except Exception:
        session.rollback()
        log.warning("[purge] purge_published_episode_mirrors failed", exc_info=True)
        raise HTTPException(status_code=500, detail="maintenance task failed")
    finally:
        session.close()

    log.info("[purge] episode mirrors: checked=%s removed_local=%s removed_remote=%s",
             checked, removed_local, removed_remote)
    
    return {
        "ok": True,
        "checked": checked,
        "removed_local": removed_local,
        "removed_remote": removed_remote
    }


# -------------------- Retry Queued Episodes --------------------

@router.post("/retry-queued-episodes")
async def retry_queued_episodes_task(request: Request, x_tasks_auth: str | None = Header(default=None)):
    """Retry queued episodes when worker server comes back online.
    
    This endpoint should be called periodically (every 1-10 minutes) to check for
    queued episodes and retry them when the worker server is available.
    
    Polling schedule:
    - First hour: every 1 minute
    - After first hour: every 10 minutes
    
    Can be called by Cloud Scheduler or a background task.
    """
    if not _IS_DEV:
        # Accept either Cloud Scheduler OIDC token OR legacy TASKS_AUTH header
        auth_header = request.headers.get("Authorization", "")
        has_oidc = auth_header.startswith("Bearer ")
        has_tasks_auth = x_tasks_auth and x_tasks_auth == _TASKS_AUTH
        
        if not (has_oidc or has_tasks_auth):
            raise HTTPException(status_code=401, detail="unauthorized")
    
    try:
        session_gen = get_session()
        session = next(session_gen)
        try:
            result = retry_queued_episodes(session)
            log.info("event=retry_queued_episodes.completed result=%s", result)
            return {"ok": True, **result}
        finally:
            session.close()
    except Exception as exc:
        log.exception("event=retry_queued_episodes.error err=%s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to retry queued episodes: {exc}")


@router.post("/maintenance/check-stuck-episodes")
async def maintenance_check_stuck_episodes(
    request: Request,
    x_tasks_auth: str | None = Header(default=None),
):
    """Check for episodes stuck in processing/queued due to Cloud Tasks/worker failures.
    
    This endpoint:
    - Finds episodes in processing/queued status for > 60 minutes
    - Checks if they have Cloud Tasks job IDs
    - Marks episodes as error if Cloud Tasks has failed or retries exhausted
    - Provides clear error messages for users
    
    Can be called by Cloud Scheduler or a background task.
    """
    if not _IS_DEV:
        # Accept either Cloud Scheduler OIDC token OR legacy TASKS_AUTH header
        auth_header = request.headers.get("Authorization", "")
        has_oidc = auth_header.startswith("Bearer ")
        has_tasks_auth = x_tasks_auth and x_tasks_auth == _TASKS_AUTH
        
        if not (has_oidc or has_tasks_auth):
            raise HTTPException(status_code=401, detail="unauthorized")
    
    try:
        from api.services.episodes.cloud_tasks_monitor import check_stuck_episodes
        session_gen = get_session()
        session = next(session_gen)
        try:
            marked = check_stuck_episodes(session, limit=100)
            log.info("event=check_stuck_episodes.completed marked=%d", marked)
            return {"ok": True, "marked_as_error": marked}
        finally:
            session.close()
    except Exception as exc:
        log.exception("event=check_stuck_episodes.error err=%s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to check stuck episodes: {exc}")

