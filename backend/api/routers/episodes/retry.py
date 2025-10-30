import json
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlmodel import select

from api.core.database import get_session
from api.routers.auth import get_current_user
from api.models.user import User
from api.models.podcast import Episode
from api.services.episodes import repo as _repo
from api.services.episodes import assembler as _svc_assembler

log = logging.getLogger("ppp.episodes.retry")

router = APIRouter(tags=["episodes"])  # parent provides '/episodes' prefix


def _status_val(s: Any) -> str:
    try:
        return s.value if hasattr(s, 'value') else str(s)
    except Exception:
        return str(s)


@router.post("/{episode_id}/retry")
def retry_episode(
    episode_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Re-enqueue assembly for an existing episode using stored metadata.

    Requirements:
      - Episode must belong to current user
      - Episode status in {'processing','error'} OR has been 'processing' longer than a safety window

    Behavior:
      - Extract saved context from Episode.meta_json (template_id, main_content_filename, output_filename, etc.)
      - Enqueue via Cloud Tasks when enabled; otherwise fall back to Celery or inline (same as assemble_or_queue).
    """
    try:
        from uuid import UUID as _UUID
        eid = _UUID(str(episode_id))
    except Exception:
        raise HTTPException(status_code=404, detail="Episode not found")

    ep = session.execute(select(Episode).where(Episode.id == eid, Episode.user_id == current_user.id)).scalars().first()
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")

    st = _status_val(getattr(ep, 'status', None)).lower()

    # Safety window: if 'processing' but likely stalled, allow retry
    import os
    from datetime import datetime, timezone, timedelta
    allow = False
    if st in {"processing", "error"}:
        allow = True
    else:
        try:
            started = getattr(ep, 'processed_at', None)
            # Heuristic: 90 minutes window if unknown duration
            window = timedelta(minutes=int(os.getenv("RETRY_PROCESSING_WINDOW_MIN", "90")))
            if started and (started.tzinfo is None or started.tzinfo.utcoffset(started) is None):
                started = started.replace(tzinfo=timezone.utc)
            if started and (datetime.now(timezone.utc) - started) > window and st == 'processing':
                allow = True
        except Exception:
            pass
    if not allow:
        raise HTTPException(status_code=409, detail="Episode not eligible for retry")

    # Pull metadata needed to requeue
    import json as _json
    meta = {}
    try:
        meta = _json.loads(getattr(ep, 'meta_json', '{}') or '{}') if getattr(ep, 'meta_json', None) else {}
    except Exception:
        meta = {}

    template_id = str(getattr(ep, 'template_id', '') or meta.get('template_id') or '').strip() or None
    main_content_filename = str(meta.get('main_content_filename') or getattr(ep, 'working_audio_name', '') or '').strip()
    output_filename = str(meta.get('output_filename') or getattr(ep, 'final_audio_path', '') or '').strip()
    tts_values = meta.get('tts_values') or {}
    episode_details = meta.get('episode_details') or {}
    intents = meta.get('intents') or None

    if not template_id or not main_content_filename:
        raise HTTPException(status_code=400, detail="Episode missing required metadata to retry")

    # Use the same assembler service as normal episode assembly
    # This ensures consistent behavior with the main assembly endpoint
    log.info("Retrying episode %s with template_id=%s, main_content=%s", 
             ep.id, template_id, main_content_filename)
    
    try:
        # Extract use_auphonic from metadata if present
        use_auphonic = meta.get('use_auphonic', False)
        
        svc_result = _svc_assembler.assemble_or_queue(
            session=session,
            current_user=current_user,
            template_id=str(template_id),
            main_content_filename=str(main_content_filename),
            output_filename=str(output_filename or ""),
            tts_values=tts_values or {},
            episode_details=episode_details or {},
            intents=intents,
            use_auphonic=use_auphonic,
        )
        
        job_id = svc_result.get("job_id", "unknown")
        mode = svc_result.get("mode", "queued")
        
        log.info("Episode %s retry dispatched: mode=%s, job_id=%s", ep.id, mode, job_id)
        
        if mode == "eager-inline":
            return {
                "message": "Episode retry completed synchronously",
                "episode_id": str(ep.id),
                "job_id": job_id,
                "status": "processed",
                "result": svc_result.get("result"),
            }
        else:
            return {
                "message": "Episode retry enqueued",
                "episode_id": str(ep.id),
                "job_id": job_id,
                "status": "queued",
            }
    
    except Exception as exc:
        log.exception("retry-failed for episode %s", ep.id)
        raise HTTPException(status_code=500, detail=f"retry-failed: {exc}")
