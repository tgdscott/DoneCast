"""Queue retry system for episodes queued when worker server is down.

Polls for queued episodes and retries them when worker server comes back online.
Polling schedule:
- First hour: every 1 minute
- After first hour: every 10 minutes
"""

from __future__ import annotations

import json
import logging
import os
import httpx
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlmodel import select

from api.models.podcast import Episode, EpisodeStatus

log = logging.getLogger("queue_retry")


def _is_worker_available(worker_url_base: str, timeout: float = 5.0) -> bool:
    """Check if worker server is available by hitting health endpoint."""
    try:
        health_url = f"{worker_url_base.rstrip('/')}/health"
        with httpx.Client(timeout=timeout) as client:
            response = client.get(health_url)
            return 200 <= response.status_code < 300
    except Exception as e:
        log.debug("event=queue_retry.worker_health_check_failed worker_url=%s error=%s", worker_url_base, str(e))
        return False


def _get_retry_interval(queued_at: datetime) -> int:
    """Get retry interval in seconds based on how long episode has been queued.
    
    Returns:
        - 60 seconds (1 minute) if queued for less than 1 hour
        - 600 seconds (10 minutes) if queued for more than 1 hour
    """
    now = datetime.now(timezone.utc)
    if queued_at.tzinfo is None:
        queued_at = queued_at.replace(tzinfo=timezone.utc)
    
    time_queued = now - queued_at
    if time_queued < timedelta(hours=1):
        return 60  # 1 minute
    else:
        return 600  # 10 minutes


def _should_retry_now(episode: Episode, queued_at: datetime, last_retry_at: Optional[datetime]) -> bool:
    """Check if episode should be retried now based on polling schedule."""
    interval_seconds = _get_retry_interval(queued_at)
    
    if last_retry_at is None:
        # Never retried - check if enough time has passed since queued
        time_since_queued = (datetime.now(timezone.utc) - queued_at).total_seconds()
        return time_since_queued >= interval_seconds
    
    if last_retry_at.tzinfo is None:
        last_retry_at = last_retry_at.replace(tzinfo=timezone.utc)
    
    time_since_last_retry = (datetime.now(timezone.utc) - last_retry_at).total_seconds()
    return time_since_last_retry >= interval_seconds


def _retry_episode_assembly(
    session: Session,
    episode: Episode,
    payload: Dict[str, Any],
    worker_url_base: str,
) -> bool:
    """Retry assembly for a queued episode.
    
    Returns:
        True if successfully dispatched to worker, False otherwise
    """
    try:
        url = f"{worker_url_base.rstrip('/')}/api/tasks/assemble"
        tasks_auth = os.getenv("TASKS_AUTH", "a-secure-local-secret")
        headers = {"Content-Type": "application/json", "X-Tasks-Auth": tasks_auth}
        timeout = 1800.0  # 30 minutes for assembly
        
        log.info("event=queue_retry.retrying_episode episode_id=%s worker_url=%s", str(episode.id), url)
        
        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, json=payload, headers=headers)
            if 200 <= response.status_code < 300:
                # Success: worker accepted the task
                log.info(
                    "event=queue_retry.episode_retried_successfully episode_id=%s status=%s",
                    str(episode.id), response.status_code
                )
                
                # Update episode status to processing
                try:
                    episode.status = EpisodeStatus.processing  # type: ignore[assignment]
                except Exception:
                    episode.status = "processing"  # type: ignore[assignment]
                
                # Update metadata to remove queue flag
                meta = {}
                if getattr(episode, 'meta_json', None):
                    try:
                        meta = json.loads(episode.meta_json or '{}')
                    except Exception:
                        meta = {}
                
                meta.pop('queued_for_worker', None)
                meta['retried_at'] = datetime.now(timezone.utc).isoformat()
                meta['assembly_job_id'] = f"queued-retry-{datetime.now(timezone.utc).isoformat()}"
                episode.meta_json = json.dumps(meta)
                
                session.add(episode)
                session.commit()
                session.refresh(episode)
                
                return True
            else:
                # Worker returned error - will retry later
                log.warning(
                    "event=queue_retry.retry_failed episode_id=%s status=%s response=%s",
                    str(episode.id), response.status_code, response.text[:200]
                )
                return False
    except Exception as e:
        log.warning(
            "event=queue_retry.retry_exception episode_id=%s error=%s",
            str(episode.id), str(e)
        )
        return False


def retry_queued_episodes(session: Session) -> Dict[str, Any]:
    """Check for queued episodes and retry them if worker is available.
    
    This function should be called frequently (every 1-2 minutes) to check for
    queued episodes. The internal logic handles the polling schedule:
    - First hour: retries every 1 minute
    - After first hour: retries every 10 minutes
    
    Returns:
        Dict with retry statistics
    """
    worker_url_base = os.getenv("WORKER_URL_BASE")
    if not worker_url_base:
        log.debug("event=queue_retry.skipped reason=no_worker_url")
        return {"skipped": True, "reason": "WORKER_URL_BASE not configured"}
    
    # Check if worker is available
    if not _is_worker_available(worker_url_base):
        log.debug("event=queue_retry.skipped reason=worker_unavailable worker_url=%s", worker_url_base)
        return {"skipped": True, "reason": "Worker server unavailable", "worker_url": worker_url_base}
    
    # Find all episodes queued for worker
    try:
        episodes = session.exec(
            select(Episode).where(
                Episode.status == EpisodeStatus.pending  # type: ignore
            )
        ).all()
    except Exception:
        # Fallback if EpisodeStatus enum doesn't work
        episodes = session.exec(
            select(Episode).where(
                Episode.status == "pending"  # type: ignore
            )
        ).all()
    
    queued_episodes = []
    for episode in episodes:
        if not getattr(episode, 'meta_json', None):
            continue
        
        try:
            meta = json.loads(episode.meta_json or '{}')
            if not meta.get('queued_for_worker'):
                continue
            
            queued_at_str = meta.get('queued_at')
            if not queued_at_str:
                continue
            
            queued_at = datetime.fromisoformat(queued_at_str.replace('Z', '+00:00'))
            last_retry_at_str = meta.get('last_retry_at')
            last_retry_at = None
            if last_retry_at_str:
                last_retry_at = datetime.fromisoformat(last_retry_at_str.replace('Z', '+00:00'))
            
            if _should_retry_now(episode, queued_at, last_retry_at):
                payload = meta.get('assembly_payload')
                if payload:
                    # Use current worker_url_base (may have changed since queuing)
                    # But prefer the queued_worker_url if it's different and valid
                    queued_worker_url = meta.get('queued_worker_url')
                    worker_url_to_use = worker_url_base
                    if queued_worker_url and queued_worker_url != worker_url_base:
                        # Try the original worker URL first
                        if _is_worker_available(queued_worker_url):
                            worker_url_to_use = queued_worker_url
                        # Otherwise use current worker_url_base
                    
                    queued_episodes.append((episode, payload, queued_at, last_retry_at, worker_url_to_use))
        except Exception as e:
            log.warning(
                "event=queue_retry.parse_episode_failed episode_id=%s error=%s",
                str(episode.id), str(e)
            )
            continue
    
    if not queued_episodes:
        log.debug("event=queue_retry.no_queued_episodes")
        return {"checked": True, "queued_count": 0, "retried_count": 0}
    
    log.info("event=queue_retry.found_queued_episodes count=%d", len(queued_episodes))
    
    # Retry each queued episode
    retried_count = 0
    failed_count = 0
    
    for episode, payload, queued_at, last_retry_at, worker_url_to_use in queued_episodes:
        try:
            # Update last_retry_at before attempting retry
            meta = json.loads(episode.meta_json or '{}')
            meta['last_retry_at'] = datetime.now(timezone.utc).isoformat()
            meta['retry_count'] = meta.get('retry_count', 0) + 1
            episode.meta_json = json.dumps(meta)
            session.add(episode)
            session.commit()
            session.refresh(episode)
            
            # Attempt retry with the worker URL (current or queued)
            success = _retry_episode_assembly(session, episode, payload, worker_url_to_use)
            if success:
                retried_count += 1
            else:
                failed_count += 1
        except Exception as e:
            log.error(
                "event=queue_retry.retry_error episode_id=%s error=%s",
                str(episode.id), str(e),
                exc_info=True
            )
            failed_count += 1
            session.rollback()
    
    return {
        "checked": True,
        "queued_count": len(queued_episodes),
        "retried_count": retried_count,
        "failed_count": failed_count,
    }

