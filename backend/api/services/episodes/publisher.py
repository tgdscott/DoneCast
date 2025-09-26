from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional
from uuid import UUID

from sqlmodel import Session, select

from . import repo
from api.services.publisher import SpreakerClient

logger = logging.getLogger("ppp.episodes.publisher.service")


def publish(session: Session, current_user, episode_id: UUID, derived_show_id: str, publish_state: Optional[str], auto_publish_iso: Optional[str]) -> Dict[str, Any]:
    ep = repo.get_episode_by_id(session, episode_id, user_id=current_user.id)
    if not ep:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Episode not found")

    if not ep.final_audio_path:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Episode is not processed yet")

    spreaker_access_token = getattr(current_user, "spreaker_access_token", None)
    if not spreaker_access_token:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="User is not connected to Spreaker")

    from worker.tasks import publish_episode_to_spreaker_task, celery_app
    task_kwargs = {
        'episode_id': str(ep.id),
        'spreaker_show_id': str(derived_show_id),
        'title': str(ep.title or "Untitled Episode"),
        'description': ep.show_notes or "",
        'auto_published_at': auto_publish_iso,
        'spreaker_access_token': spreaker_access_token,
        'publish_state': publish_state,
    }

    def _run_inline_publish() -> Dict[str, Any]:
        try:
            result = publish_episode_to_spreaker_task.apply(args=(), kwargs=task_kwargs)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("[publish] Inline publish task raised", exc_info=True)
            raise exc
        payload = getattr(result, 'result', None)
        return {"job_id": "inline", "result": payload}

    eager = False
    try:
        eager = bool(getattr(celery_app.conf, 'task_always_eager', False))
    except Exception:
        eager = False
    if eager:
        # Execute synchronously for dev reliability
        result = publish_episode_to_spreaker_task.apply(args=(), kwargs=task_kwargs)
        return {"job_id": "eager", "result": getattr(result, 'result', None)}

    try:
        async_result = publish_episode_to_spreaker_task.apply_async(kwargs=task_kwargs)
    except Exception:
        logger.warning("[publish] Celery enqueue failed; running inline", exc_info=True)
        return _run_inline_publish()

    auto_fallback = os.getenv("CELERY_AUTO_FALLBACK", "").strip().lower() in {"1", "true", "yes", "on"}
    env = os.getenv("APP_ENV", "dev").strip().lower()
    if auto_fallback or env in {"dev", "development", "local"}:
        needs_fallback = False
        try:
            ping = celery_app.control.ping(timeout=1)
            if not ping:
                needs_fallback = True
        except Exception:
            needs_fallback = True
        if needs_fallback:
            logger.warning("[publish] No Celery workers detected; executing inline fallback")
            return _run_inline_publish()

    return {"job_id": async_result.id}


def unpublish(session: Session, current_user, episode_id: UUID, force: bool = False) -> Dict[str, Any]:
    from datetime import datetime, timezone, timedelta
    ep = repo.get_episode_by_id(session, episode_id, user_id=current_user.id)
    if not ep:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Episode not found")

    now = datetime.now(timezone.utc)
    publish_at = getattr(ep, 'publish_at', None)
    if publish_at and (publish_at.tzinfo is None or publish_at.tzinfo.utcoffset(publish_at) is None):
        publish_at = publish_at.replace(tzinfo=timezone.utc)
    is_scheduled = bool(publish_at and publish_at > now)

    base_status = str(getattr(ep.status, 'value', ep.status))
    if base_status != 'published' and not is_scheduled:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Episode is not published or scheduled")

    # For scheduled episodes, skip retention checks. For published, enforce 24h window unless forced.
    within_retention = True
    if not is_scheduled:
        published_at = publish_at or getattr(ep, 'processed_at', None)
        if published_at:
            if published_at.tzinfo is None or published_at.tzinfo.utcoffset(published_at) is None:
                published_at = published_at.replace(tzinfo=timezone.utc)
            within_retention = (now - published_at) <= timedelta(hours=24)
        if not within_retention and not force:
            from fastapi import HTTPException
            raise HTTPException(status_code=409, detail="Outside retention window; force required")

    # Best-effort remote delete (works for both published and scheduled if remote exists)
    spk_id = getattr(ep, 'spreaker_episode_id', None)
    token = getattr(current_user, 'spreaker_access_token', None)
    removed_remote = False
    remote_error = None
    if spk_id and token:
        try:
            client = SpreakerClient(token)
            r = client.session.delete(f"{client.BASE_URL}/episodes/{spk_id}")
            if r.status_code == 404 or (r.status_code // 100 == 2):
                removed_remote = True
            else:
                remote_error = f"DELETE /episodes/{spk_id} -> {r.status_code}: {r.text[:180]}"
        except Exception as ex:
            remote_error = str(ex)
    elif is_scheduled:
        # Allow local cancellation even if remote id not yet recorded.
        remote_error = "no_spreaker_id"

    # Local revert / unschedule
    try:
        try:
            from api.models.podcast import EpisodeStatus
            ep.status = EpisodeStatus.processed  # type: ignore[assignment]
        except Exception:
            ep.status = 'processed'  # type: ignore[assignment]
        ep.is_published_to_spreaker = False
        ep.spreaker_episode_id = None
        ep.publish_at = None
        # Clear user-facing local time string as well
        if hasattr(ep, 'publish_at_local'):
            ep.publish_at_local = None
        session.add(ep)
        session.commit()
        session.refresh(ep)
    except Exception:
        session.rollback()
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail="Failed to update episode state locally")

    return {
        "message": ("Scheduled publish canceled" if is_scheduled else "Episode reverted to processed"),
        "episode_id": str(ep.id),
        "removed_remote": removed_remote,
        "remote_error": remote_error,
        "within_retention_window": True if is_scheduled else within_retention,
        "forced": False if is_scheduled else (force and not within_retention),
        "was_scheduled": is_scheduled,
    }


def republish(session: Session, current_user, episode_id: UUID) -> Dict[str, Any]:
    """Republish an already assembled episode using its associated podcast show id.

    Returns dict with keys: job_id, spreaker_show_id
    """
    ep = repo.get_episode_by_id(session, episode_id, user_id=current_user.id)
    if not ep:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Episode not found")
    if not ep.final_audio_path:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Episode has no final audio to publish")
    if not getattr(ep, 'podcast_id', None):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Episode is not linked to a show")

    spreaker_access_token = getattr(current_user, "spreaker_access_token", None)
    if not spreaker_access_token:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="User is not connected to Spreaker")

    # Resolve show id from associated podcast
    show_id = None
    try:
        from api.models.podcast import Podcast
        pod = session.exec(select(Podcast).where(Podcast.id == ep.podcast_id)).first()
        if pod and getattr(pod, 'spreaker_show_id', None):
            show_id = str(pod.spreaker_show_id)
    except Exception:
        show_id = None
    if not show_id or not show_id.isdigit():
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Associated show spreaker_show_id must be numeric")

    # Clear republish flags before re-sending
    try:
        ep.spreaker_publish_error = None
        ep.spreaker_publish_error_detail = None
        ep.needs_republish = False
        session.add(ep)
        session.commit()
    except Exception:
        session.rollback()
    from worker.tasks import publish_episode_to_spreaker_task
    async_result = publish_episode_to_spreaker_task.delay(
        episode_id=str(ep.id),
        spreaker_show_id=show_id,
        title=str(ep.title or "Untitled Episode"),
        description=ep.show_notes or "",
        auto_published_at=None,
        spreaker_access_token=spreaker_access_token,
        publish_state="public",
    )
    return {"job_id": async_result.id, "spreaker_show_id": show_id}


def refresh_remote(session: Session, current_user, episode_id: UUID) -> Dict[str, Any]:
    """Fetch latest remote episode data from Spreaker and update local fields.

    Returns an object with keys: refreshed (bool), reason/error, episode_id, remote_title (optional)
    """
    from fastapi import HTTPException
    ep = repo.get_episode_by_id(session, episode_id, user_id=current_user.id)
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")
    spk_id = getattr(ep, 'spreaker_episode_id', None)
    if not spk_id:
        return {"refreshed": False, "reason": "no_spreaker_id", "episode_id": str(ep.id)}
    token = getattr(current_user, 'spreaker_access_token', None)
    if not token:
        raise HTTPException(status_code=401, detail="User not connected to Spreaker")
    try:
        client = SpreakerClient(token)
        ok, resp = client.get_episode(spk_id)
        if not ok:
            return {"refreshed": False, "error": resp, "episode_id": str(ep.id)}
        remote = resp.get('episode') if isinstance(resp, dict) and 'episode' in resp else resp
        cover_before = getattr(ep, 'remote_cover_url', None)
        if isinstance(remote, dict):
            new_remote_cover = remote.get('image_url') or remote.get('image_original_url')
            if new_remote_cover and new_remote_cover != cover_before:
                ep.remote_cover_url = new_remote_cover
                session.add(ep)
                session.commit()
        return {
            "refreshed": True,
            "episode_id": str(ep.id),
            "remote_title": remote.get('title') if isinstance(remote, dict) else None,
        }
    except HTTPException:
        raise
    except Exception as ex:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(ex))
