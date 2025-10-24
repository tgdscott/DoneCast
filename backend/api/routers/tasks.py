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
    user_id: str | None = None  # Optional: determines which transcription service to use


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
    *, 
    suppress_errors: bool
) -> None:
    """Execute transcription in a worker thread, optionally suppressing exceptions."""
    loop = asyncio.get_running_loop()
    log.info("event=tasks.transcribe.start filename=%s user_id=%s request_id=%s", filename, user_id, request_id)
    try:
        await loop.run_in_executor(None, transcribe_media_file, filename, user_id)
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
    user_id = (payload.user_id or "").strip() or None  # Extract user_id from payload
    
    if not filename:
        raise HTTPException(status_code=400, detail="filename required")

    request_id = request.headers.get("x-request-id")

    if _IS_DEV:
        _ensure_local_media_present(filename)
        asyncio.create_task(_dispatch_transcription(filename, user_id, request_id, suppress_errors=True))
        return {"started": True, "async": True}

    try:
        await _dispatch_transcription(filename, user_id, request_id, suppress_errors=False)
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
        daemon=False,  # Allow process to finish even if parent exits
    )
    process.start()
    log.info("event=tasks.assemble.dispatched episode_id=%s pid=%s", payload.episode_id, process.pid)
    
    # Return immediately with 202 Accepted
    return {"ok": True, "status": "processing", "episode_id": payload.episode_id}


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
        payload = _validate_process_chunk_payload(data)
    except ValidationError as ve:
        raise HTTPException(status_code=400, detail=f"invalid payload: {ve}")

    # Execute asynchronously in separate process
    def _run_chunk_processing():
        try:
            import sys
            import logging
            import tempfile
            from pathlib import Path
            from pydub import AudioSegment
            
            # Configure logging in child process
            logging.basicConfig(
                level=logging.INFO,
                format='[%(asctime)s] %(levelname)s %(name)s: %(message)s',
                stream=sys.stdout
            )
            log = logging.getLogger("tasks.process_chunk.worker")
            
            log.info("event=chunk.start episode_id=%s chunk_id=%s pid=%s",
                    payload.episode_id, payload.chunk_id, os.getpid())
            
            # Import required modules
            import infrastructure.gcs as gcs
            
            # Create temp directory for this chunk
            with tempfile.TemporaryDirectory(prefix=f"chunk_{payload.chunk_index}_") as tmpdir:
                tmpdir_path = Path(tmpdir)
                
                # Download chunk audio from GCS
                log.info("event=chunk.download uri=%s", payload.gcs_audio_uri)
                chunk_audio_path = tmpdir_path / f"chunk_{payload.chunk_index}.wav"
                
                # Parse GCS URI: gs://bucket/path/to/file
                gcs_uri = payload.gcs_audio_uri
                if gcs_uri.startswith("gs://"):
                    parts = gcs_uri[5:].split("/", 1)
                    if len(parts) == 2:
                        bucket_name, blob_path = parts
                        audio_bytes = gcs.download_gcs_bytes(bucket_name, blob_path)
                        if audio_bytes:
                            chunk_audio_path.write_bytes(audio_bytes)
                            log.info("event=chunk.downloaded size=%d", len(audio_bytes))
                        else:
                            log.error("event=chunk.download_failed uri=%s", gcs_uri)
                            return
                
                # Download chunk transcript if available
                transcript_data = None
                if payload.gcs_transcript_uri:
                    log.info("event=chunk.download_transcript uri=%s", payload.gcs_transcript_uri)
                    gcs_uri = payload.gcs_transcript_uri
                    if gcs_uri.startswith("gs://"):
                        parts = gcs_uri[5:].split("/", 1)
                        if len(parts) == 2:
                            bucket_name, blob_path = parts
                            transcript_bytes = gcs.download_gcs_bytes(bucket_name, blob_path)
                            if transcript_bytes:
                                import json
                                transcript_data = json.loads(transcript_bytes.decode("utf-8"))
                                # Handle both list and dict formats
                                if isinstance(transcript_data, list):
                                    word_count = len(transcript_data)
                                elif isinstance(transcript_data, dict):
                                    word_count = len(transcript_data.get("words", []))
                                else:
                                    word_count = 0
                                log.info("event=chunk.transcript_downloaded words=%d", word_count)
                
                # Run audio cleaning on chunk
                log.info("event=chunk.clean_start chunk_path=%s", chunk_audio_path)
                cleanup_opts = payload.cleanup_options or {}
                
                # Load audio
                audio = AudioSegment.from_file(str(chunk_audio_path))
                log.info("event=chunk.loaded duration_ms=%d", len(audio))
                
                # Apply chunk-level cleaning (parallel processing)
                from api.services.audio.cleanup import rebuild_audio_from_words, compress_long_pauses_guarded
                
                cleaned_audio = audio
                mutable_words = transcript_data if isinstance(transcript_data, list) else (transcript_data.get("words", []) if transcript_data else [])
                
                # 1. Remove filler words if configured
                if cleanup_opts.get("removeFillers", True) and mutable_words:
                    filler_words_list = cleanup_opts.get("fillerWords", []) or []
                    filler_words = set([str(w).strip().lower() for w in filler_words_list if str(w).strip()])
                    if filler_words:
                        log.info("event=chunk.removing_fillers count=%d", len(filler_words))
                        cleaned_audio, _, _ = rebuild_audio_from_words(
                            audio,
                            mutable_words,
                            filler_words=filler_words,
                            remove_fillers=True,
                            filler_lead_trim_ms=int(cleanup_opts.get('fillerLeadTrimMs', 60)),
                            log=[],
                        )
                
                # 2. Compress long pauses if configured
                if cleanup_opts.get("removePauses", True):
                    log.info("event=chunk.compressing_pauses")
                    cleaned_audio = compress_long_pauses_guarded(
                        cleaned_audio,
                        max_pause_s=float(cleanup_opts.get('maxPauseSeconds', 1.5)),
                        min_target_s=float(cleanup_opts.get('targetPauseSeconds', 0.5)),
                        ratio=float(cleanup_opts.get('pauseCompressionRatio', 0.4)),
                        rel_db=16.0,
                        removal_guard_pct=float(cleanup_opts.get('maxPauseRemovalPct', 0.1)),
                        similarity_guard=float(cleanup_opts.get('pauseSimilarityGuard', 0.85)),
                        log=[],
                    )
                
                # 3. Trim trailing silence from last chunk (prevents gap before outro)
                # The transcript ends at the last word, but audio may continue with silence
                # This is only needed for the final chunk since middle chunks join seamlessly
                is_last_chunk = (payload.chunk_index == payload.total_chunks - 1)
                if is_last_chunk and mutable_words:
                    # Find the end time of the last word in transcript
                    last_word_end_ms = 0
                    for w in mutable_words:
                        word_end = w.get("end", 0) * 1000  # Convert to ms
                        if word_end > last_word_end_ms:
                            last_word_end_ms = word_end
                    
                    # Add a small buffer after last word (500ms) to avoid cutting off speech
                    trim_point_ms = int(last_word_end_ms + 500)
                    
                    if trim_point_ms < len(cleaned_audio):
                        log.info("event=chunk.trim_trailing_silence last_word_end=%d trim_point=%d audio_duration=%d",
                                last_word_end_ms, trim_point_ms, len(cleaned_audio))
                        cleaned_audio = cleaned_audio[:trim_point_ms]
                
                log.info("event=chunk.cleaned original_ms=%d cleaned_ms=%d", len(audio), len(cleaned_audio))
                
                # Export cleaned audio
                cleaned_audio_path = tmpdir_path / f"chunk_{payload.chunk_index}_cleaned.mp3"
                log.info("event=chunk.export path=%s", cleaned_audio_path)
                cleaned_audio.export(str(cleaned_audio_path), format="mp3")
                
                # Upload cleaned chunk to GCS
                cleaned_gcs_path = payload.gcs_audio_uri.replace(".wav", "_cleaned.mp3").replace("gs://ppp-media-us-west1/", "")
                log.info("event=chunk.upload path=%s", cleaned_gcs_path)
                
                cleaned_bytes = cleaned_audio_path.read_bytes()
                cleaned_uri = gcs.upload_bytes("ppp-media-us-west1", cleaned_gcs_path, cleaned_bytes, content_type="audio/mpeg")
                
                log.info("event=chunk.complete episode_id=%s chunk_id=%s cleaned_uri=%s",
                        payload.episode_id, payload.chunk_id, cleaned_uri)
                
                # TODO: Update episode metadata to mark chunk as completed
                # This would require database access - for now, we rely on polling
                
        except Exception as exc:  # pragma: no cover - defensive
            import logging
            log = logging.getLogger("tasks.process_chunk.worker")
            log.exception("event=chunk.error episode_id=%s chunk_id=%s err=%s",
                         payload.episode_id, payload.chunk_id, exc)

    import multiprocessing
    process = multiprocessing.Process(
        target=_run_chunk_processing,
        name=f"chunk-{payload.chunk_id}",
        daemon=False,  # CRITICAL: Allow process to finish even if parent exits
    )
    process.start()
    log.info("event=chunk.dispatched episode_id=%s chunk_id=%s pid=%s",
            payload.episode_id, payload.chunk_id, process.pid)
    
    return {"ok": True, "status": "processing", "chunk_id": payload.chunk_id}

