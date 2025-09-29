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

    # Build payload for tasks
    payload = {
        "episode_id": str(ep.id),
        "template_id": str(template_id),
        "main_content_filename": str(main_content_filename),
        "output_filename": str(output_filename or ""),
        "tts_values": tts_values,
        "episode_details": episode_details,
        "user_id": str(current_user.id),
        "podcast_id": str(getattr(ep, 'podcast_id', '') or ''),
        "intents": intents,
    }

    # Prefer Cloud Tasks HTTP path for consistency
    use_cloud = (os.getenv("USE_CLOUD_TASKS", "").strip().lower() in {"1","true","yes","on"})
    job_name = None
    if use_cloud:
        try:
            from infrastructure.tasks_client import enqueue_http_task  # type: ignore
            info = enqueue_http_task("/api/tasks/assemble", payload)
            job_name = info.get('name') or 'cloud-task'
        except Exception:
            job_name = None

    if job_name is None:
        # Fallback to Celery direct call or inline
        try:
            from worker.tasks import create_podcast_episode
            create_podcast_episode(
                episode_id=str(ep.id),
                template_id=str(template_id),
                main_content_filename=str(main_content_filename),
                output_filename=str(output_filename or ""),
                tts_values=tts_values or {},
                episode_details=episode_details or {},
                user_id=str(current_user.id),
                podcast_id=str(getattr(ep, 'podcast_id', '') or ''),
                intents=intents or None,
            )
            job_name = "inline"
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"retry-failed: {exc}")

    # Update episode status back to processing and store assembly_job_id
    try:
        try:
            from api.models.podcast import EpisodeStatus as _EpStatus
            ep.status = _EpStatus.processing  # type: ignore
        except Exception:
            setattr(ep, 'status', 'processing')
        if hasattr(ep, 'processed_at'):
            from datetime import datetime as _dt
            ep.processed_at = _dt.utcnow()
        meta = meta or {}
        meta['assembly_job_id'] = job_name
        ep.meta_json = json.dumps(meta)
        session.add(ep)
        session.commit()
    except Exception:
        session.rollback()

    return {"job_id": job_name, "status": "queued", "episode_id": str(ep.id)}
