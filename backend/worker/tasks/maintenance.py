"""Maintenance tasks for detecting and cleaning up stuck operations.

This module provides utilities to detect operations that are stuck in
processing state and need intervention.
"""
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
from sqlmodel import Session, select
import logging

from api.models.episode import Episode, EpisodeStatus

log = logging.getLogger(__name__)


def detect_stuck_episodes(
    session: Session,
    stuck_threshold_hours: int = 2,
) -> List[Dict[str, Any]]:
    """Detect episodes stuck in processing state.
    
    Args:
        session: Database session
        stuck_threshold_hours: Hours after which an episode is considered stuck
    
    Returns:
        List of stuck episode details
    """
    stuck_threshold = datetime.now(timezone.utc) - timedelta(hours=stuck_threshold_hours)
    
    stuck_episodes = session.exec(
        select(Episode).where(
            Episode.status == EpisodeStatus.processing,
            Episode.processed_at < stuck_threshold
        )
    ).all()
    
    results = []
    for ep in stuck_episodes:
        results.append({
            "id": str(ep.id),
            "user_id": str(ep.user_id),
            "stuck_since": ep.processed_at.isoformat() if ep.processed_at else None,
            "type": "episode_assembly",
            "status": ep.status.value if hasattr(ep.status, "value") else str(ep.status),
        })
    
    if results:
        log.warning(
            "Detected %d stuck episodes (processing > %d hours)",
            len(results),
            stuck_threshold_hours
        )
    
    return results


def mark_stuck_episodes_as_error(
    session: Session,
    stuck_threshold_hours: int = 2,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """Mark stuck episodes as error state.
    
    Args:
        session: Database session
        stuck_threshold_hours: Hours after which an episode is considered stuck
        dry_run: If True, only detect but don't modify
    
    Returns:
        Summary of actions taken
    """
    stuck_episodes = detect_stuck_episodes(session, stuck_threshold_hours)
    
    if not stuck_episodes:
        return {
            "stuck_count": 0,
            "marked_as_error": 0,
            "dry_run": dry_run,
        }
    
    marked_count = 0
    if not dry_run:
        for ep_info in stuck_episodes:
            try:
                episode = session.get(Episode, ep_info["id"])
                if episode and episode.status == EpisodeStatus.processing:
                    episode.status = EpisodeStatus.error
                    # Add error reason to metadata if available
                    if hasattr(episode, "meta_json") and episode.meta_json:
                        meta = episode.meta_json.copy() if isinstance(episode.meta_json, dict) else {}
                        meta["error_reason"] = "operation_timeout"
                        meta["marked_stuck_at"] = datetime.now(timezone.utc).isoformat()
                        episode.meta_json = meta
                    marked_count += 1
                    log.info(
                        "Marked stuck episode %s as error (stuck since %s)",
                        ep_info["id"],
                        ep_info["stuck_since"]
                    )
            except Exception as e:
                log.error(
                    "Failed to mark episode %s as error: %s",
                    ep_info["id"],
                    e,
                    exc_info=True
                )
        
        if marked_count > 0:
            try:
                session.commit()
            except Exception as e:
                log.error("Failed to commit stuck episode updates: %s", e, exc_info=True)
                session.rollback()
                marked_count = 0
    
    return {
        "stuck_count": len(stuck_episodes),
        "marked_as_error": marked_count if not dry_run else 0,
        "dry_run": dry_run,
        "stuck_episodes": stuck_episodes if dry_run else None,  # Only include details in dry_run
    }
