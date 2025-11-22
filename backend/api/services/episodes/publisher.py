from __future__ import annotations

import logging
import os
from importlib import import_module
from importlib.util import find_spec
from typing import Any, Dict, Optional, Tuple
from uuid import UUID
from datetime import datetime, timezone

from sqlmodel import Session, select

from . import repo
from api.services.publisher import SpreakerClient
from api.services.sms import sms_service
from api.models.user import User

logger = logging.getLogger("ppp.episodes.publisher.service")

# Celery has been removed - Spreaker publishing is LEGACY only (kept for backward compatibility)
# All new episodes publish directly to GCS/RSS, not Spreaker
publish_episode_to_spreaker_task: Optional[Any] = None
_worker_import_attempted = False
_worker_import_error: Optional[BaseException] = None


def _load_publish_task() -> None:
    """Attempt to import the legacy Spreaker publish task exactly once."""

    global publish_episode_to_spreaker_task, _worker_import_attempted, _worker_import_error

    if publish_episode_to_spreaker_task is not None or _worker_import_attempted:
        return

    _worker_import_attempted = True
    module_candidates = ("worker.tasks", "backend.worker.tasks")
    last_error: Optional[BaseException] = None

    for module_name in module_candidates:
        try:
            spec = find_spec(module_name)
        except Exception as exc:  # pragma: no cover - defensive guard
            last_error = exc
            continue

        if spec is None:
            continue

        try:
            module = import_module(module_name)
            task = getattr(module, "publish_episode_to_spreaker_task", None)
            if task is None:
                raise AttributeError(f"publish_episode_to_spreaker_task missing from {module_name}")
            publish_episode_to_spreaker_task = task
            _worker_import_error = None
            return
        except Exception as exc:  # pragma: no cover - defensive guard
            last_error = exc
            continue

    _worker_import_error = last_error or ImportError(
        "publish_episode_to_spreaker_task not found in worker tasks"
    )


def _ensure_publish_task_available() -> None:
    """Raise a HTTP 503 if the publish task is unavailable (Spreaker is legacy/disabled)."""

    _load_publish_task()

    # Celery and Spreaker publishing are disabled
    if publish_episode_to_spreaker_task is not None:
        return

    from fastapi import HTTPException  # Local import to avoid FastAPI dependency at module import

    raise HTTPException(
        status_code=503,
        detail={
            "code": "PUBLISH_WORKER_UNAVAILABLE",
            "message": "Episode publish worker is not available. Please try again later or contact support.",
            "import_error": repr(_worker_import_error) if _worker_import_error else None,
        },
    )


def publish(session: Session, current_user, episode_id: UUID, derived_show_id: Optional[str], publish_state: Optional[str], auto_publish_iso: Optional[str]) -> Dict[str, Any]:
    # DON'T check worker availability until we know we need Spreaker
    # Many users don't have Spreaker and should publish RSS-only without errors

    ep = repo.get_episode_by_id(session, episode_id, user_id=current_user.id)
    if not ep:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Episode not found")

    if not ep.final_audio_path:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Episode is not processed yet")

    # Spreaker is now OPTIONAL - allow RSS-only publishing
    spreaker_access_token = getattr(current_user, "spreaker_access_token", None)
    
    # Skip Spreaker task if no token or no show ID (RSS-only mode)
    if not spreaker_access_token or not derived_show_id:
        logger.info(
            "publish: RSS-only mode (spreaker_token=%s show_id=%s auto_publish=%s) episode_id=%s",
            bool(spreaker_access_token),
            derived_show_id,
            auto_publish_iso,
            episode_id
        )
        # Update episode status based on whether it's scheduled or immediate
        from api.models.podcast import EpisodeStatus
        
        if auto_publish_iso:
            # Scheduled publish - keep status as "processed" until scheduled time
            # (Frontend determines "scheduled" by checking processed + future publish_at)
            ep.status = EpisodeStatus.processed
            message = f"Episode scheduled for {auto_publish_iso} (RSS feed only)"
            publish_date = datetime.fromisoformat(auto_publish_iso.replace('Z', '+00:00')) if auto_publish_iso else None
        else:
            # Immediate publish - set to published
            ep.status = EpisodeStatus.published
            message = "Episode published to RSS feed (Spreaker not configured)"
            publish_date = datetime.now(timezone.utc)
        
        session.add(ep)
        session.commit()
        session.refresh(ep)
        
        # Hide coming soon episode if this is a real episode being published
        if ep.status == EpisodeStatus.published and ep.episode_type != "trailer":
            try:
                from ...services.episodes.coming_soon import hide_coming_soon_episode_if_needed
                hide_coming_soon_episode_if_needed(session, ep.podcast_id)
            except Exception as hide_err:
                # Non-fatal - log but don't fail publish
                logger.warning(f"Failed to hide coming soon episode (non-fatal): {hide_err}")
        
        # Send SMS notification if user has opted in
        try:
            user = session.get(User, current_user.id)
            # Use getattr() to safely access SMS fields (may not exist if migration hasn't run)
            sms_enabled = getattr(user, 'sms_notifications_enabled', False) if user else False
            sms_publish = getattr(user, 'sms_notify_publish', False) if user else False
            phone_number = getattr(user, 'phone_number', None) if user else None
            
            if user and sms_enabled and sms_publish and phone_number:
                episode_name = ep.title or "Untitled Episode"
                sms_service.send_publish_notification(
                    phone_number=phone_number,
                    episode_name=episode_name,
                    publish_date=publish_date,
                    user_id=str(user.id)
                )
                logger.info("[publish] SMS notification sent to user %s for episode %s", user.id, episode_name)
        except Exception as sms_err:
            # Don't fail the publish if SMS fails (or if columns don't exist yet)
            logger.warning("[publish] SMS notification failed for user %s: %s", current_user.id, sms_err, exc_info=True)
        
        return {
            "job_id": "rss-only",
            "message": message
        }

    # Only check Spreaker worker availability if we actually need it
    _ensure_publish_task_available()

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
            from typing import cast as _cast, Any as _Any
            _task = _cast(_Any, publish_episode_to_spreaker_task)
            result = _task.apply(args=(), kwargs=task_kwargs)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("[publish] Inline publish task raised", exc_info=True)
            raise exc
        payload = getattr(result, 'result', None)
        return {"job_id": "inline", "result": payload}

    # Celery removed - no worker probing needed
    # Spreaker publishing is legacy only, should not be called for new episodes
    # Always use inline fallback if this code path is reached
    logger.warning("[publish] Spreaker publishing called (legacy) - using inline execution")
    inline_result = _run_inline_publish()
    inline_result["worker_status"] = {"available": False, "detail": "celery_removed"}
    return inline_result

    try:
        from typing import cast as _cast, Any as _Any
        _task = _cast(_Any, publish_episode_to_spreaker_task)
        async_result = _task.apply_async(kwargs=task_kwargs)
    except Exception as exc:
        logger.warning("[publish] Celery enqueue failed; running inline", exc_info=True)
        inline_result = _run_inline_publish()
        inline_result.setdefault(
            "worker_status",
            {"available": False, "detail": f"apply_async failed: {exc}"},
        )
        return inline_result

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
        
        # Only clear Spreaker episode ID if we successfully removed it from Spreaker
        # Otherwise keep it as a fallback audio source (stream URL)
        if removed_remote:
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
    _ensure_publish_task_available()

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
    from typing import cast as _cast, Any as _Any
    _task = _cast(_Any, publish_episode_to_spreaker_task)
    async_result = _task.delay(
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
