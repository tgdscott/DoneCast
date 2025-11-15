"""Monitor Cloud Tasks execution and detect failures for episodes.

This module handles detection of Cloud Tasks failures and worker endpoint errors,
marking episodes as error when retries are exhausted or failures are detected.
"""
import json
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from uuid import UUID

from sqlalchemy.orm import Session
from sqlmodel import select

from api.models.podcast import Episode, EpisodeStatus

log = logging.getLogger("assemble.monitor")

# Maximum number of consecutive non-2xx HTTP responses before marking as error
MAX_CONSECUTIVE_FAILURES = 3

# Time window for checking stuck episodes (episodes in processing/queued for this long)
STUCK_EPISODE_WINDOW_MINUTES = 60


def _get_cloud_tasks_client():
    """Get Cloud Tasks client if available."""
    try:
        from google.cloud import tasks_v2
        return tasks_v2.CloudTasksClient()
    except ImportError:
        return None


def _parse_task_name(task_name: str) -> Optional[Dict[str, str]]:
    """Parse Cloud Tasks task name to extract project, location, queue, and task ID.
    
    Format: projects/{project}/locations/{location}/queues/{queue}/tasks/{task_id}
    """
    try:
        parts = task_name.split("/")
        if len(parts) == 8 and parts[0] == "projects" and parts[2] == "locations":
            return {
                "project": parts[1],
                "location": parts[3],
                "queue": parts[5],
                "task_id": parts[7],
            }
    except Exception:
        pass
    return None


def check_cloud_tasks_status(task_name: str) -> Optional[Dict[str, Any]]:
    """Check the status of a Cloud Tasks task.
    
    Returns:
        Dict with status information, or None if unable to check.
        Keys: 'status' (str), 'response_code' (int, optional), 'error' (str, optional)
    """
    client = _get_cloud_tasks_client()
    if not client:
        log.debug("Cloud Tasks client not available, cannot check task status")
        return None
    
    try:
        parsed = _parse_task_name(task_name)
        if not parsed:
            log.warning("Invalid task name format: %s", task_name)
            return None
        
        # Get task details
        task_path = client.task_path(
            parsed["project"],
            parsed["location"],
            parsed["queue"],
            parsed["task_id"]
        )
        
        task = client.get_task(request={"name": task_path})
        
        # Check task execution attempts
        # Cloud Tasks doesn't expose final status directly, but we can check:
        # 1. If task has been deleted (executed and cleaned up)
        # 2. If task has dispatch_count > max_retries (failed)
        # 3. Response codes from execution attempts
        
        result = {
            "status": "unknown",
            "task_name": task_name,
        }
        
        # Note: Cloud Tasks API doesn't directly expose execution status
        # We need to rely on other signals (like checking if task still exists,
        # or monitoring HTTP response codes from the endpoint)
        
        # For now, we'll use a heuristic: if task exists and hasn't been deleted,
        # it's either pending or being retried
        # We'll need to check episode status and time to determine if it's stuck
        
        return result
        
    except Exception as e:
        # Task might not exist (already executed and cleaned up) or other error
        log.debug("Could not check Cloud Tasks status for %s: %s", task_name, e)
        return None


def _mark_episode_worker_error(
    session: Session,
    episode: Episode,
    error_type: str,
    error_message: str,
    error_details: Optional[Dict[str, Any]] = None,
) -> None:
    """Mark an episode as error due to worker/Cloud Tasks failure."""
    try:
        from api.models.podcast import EpisodeStatus as EpStatus
        episode.status = EpStatus.error  # type: ignore[assignment]
    except Exception:
        episode.status = "error"  # type: ignore[assignment]
    
    # Store error details in metadata
    try:
        meta = {}
        if getattr(episode, 'meta_json', None):
            try:
                meta = json.loads(episode.meta_json or '{}')
            except Exception:
                meta = {}
        
        meta['worker_error'] = {
            'type': error_type,
            'message': error_message,
            'detected_at': datetime.now(timezone.utc).isoformat(),
        }
        if error_details:
            meta['worker_error'].update(error_details)
        
        episode.meta_json = json.dumps(meta)
        session.add(episode)
        session.commit()
        
        log.error(
            "event=assemble.monitor.episode_marked_error episode_id=%s error_type=%s message=%s",
            str(episode.id), error_type, error_message
        )
    except Exception as e:
        log.error(
            "event=assemble.monitor.mark_error_failed episode_id=%s error=%s",
            str(episode.id), str(e),
            exc_info=True
        )
        session.rollback()


def check_stuck_episodes(session: Session, limit: int = 50) -> int:
    """Check for episodes stuck in processing/queued status and mark as error if needed.
    
    This function:
    1. Finds episodes in 'processing' or 'queued' status for > STUCK_EPISODE_WINDOW_MINUTES
    2. Checks if they have Cloud Tasks job IDs
    3. Attempts to determine if Cloud Tasks has failed
    4. Marks episodes as error with clear messages
    
    Returns:
        Number of episodes marked as error
    """
    try:
        from api.models.podcast import EpisodeStatus as EpStatus
    except Exception:
        EpStatus = None
    
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=STUCK_EPISODE_WINDOW_MINUTES)
    
    # Find stuck episodes
    try:
        if EpStatus:
            status_filter = (Episode.status.in_([EpStatus.processing, EpStatus.pending]))  # type: ignore
        else:
            status_filter = (Episode.status.in_(["processing", "pending"]))  # type: ignore
        
        stuck_episodes = session.exec(
            select(Episode)
            .where(status_filter)
            .where(Episode.processed_at <= cutoff)  # type: ignore
            .limit(limit)
        ).all()
    except Exception as e:
        log.error("event=assemble.monitor.query_failed error=%s", str(e), exc_info=True)
        return 0
    
    marked_count = 0
    
    for episode in stuck_episodes:
        try:
            # Check if episode has Cloud Tasks job ID
            meta = {}
            if getattr(episode, 'meta_json', None):
                try:
                    meta = json.loads(episode.meta_json or '{}')
                except Exception:
                    meta = {}
            
            job_id = meta.get('assembly_job_id')
            if not job_id:
                # No job ID - might be queued for worker or using different dispatch
                # Check if it's been stuck too long
                time_stuck = (datetime.now(timezone.utc) - episode.processed_at.replace(tzinfo=timezone.utc)).total_seconds() / 60
                if time_stuck > STUCK_EPISODE_WINDOW_MINUTES * 2:  # Double the window
                    _mark_episode_worker_error(
                        session,
                        episode,
                        "stuck_no_job_id",
                        "Episode has been stuck in processing for an extended period. "
                        "No assembly job ID found. Please retry the episode.",
                        {"time_stuck_minutes": int(time_stuck)}
                    )
                    marked_count += 1
                continue
            
            # Check if this is a Cloud Tasks job
            if "projects/" in str(job_id) or "cloud-task" in str(job_id).lower():
                # Try to check Cloud Tasks status
                task_status = check_cloud_tasks_status(str(job_id))
                
                # For now, if episode is stuck and has a Cloud Tasks job ID,
                # mark it as error with a helpful message
                # (Cloud Tasks API doesn't expose final status easily, so we use time-based heuristic)
                time_stuck = (datetime.now(timezone.utc) - episode.processed_at.replace(tzinfo=timezone.utc)).total_seconds() / 60
                
                if time_stuck > STUCK_EPISODE_WINDOW_MINUTES * 2:
                    _mark_episode_worker_error(
                        session,
                        episode,
                        "cloud_tasks_stuck",
                        "Episode assembly appears to have failed. "
                        "The Cloud Tasks job may have exhausted retries or encountered persistent errors. "
                        "Please retry the episode or contact support if the issue persists.",
                        {
                            "job_id": str(job_id),
                            "time_stuck_minutes": int(time_stuck),
                            "task_status": task_status,
                        }
                    )
                    marked_count += 1
            
        except Exception as e:
            log.error(
                "event=assemble.monitor.check_episode_failed episode_id=%s error=%s",
                str(episode.id), str(e),
                exc_info=True
            )
            continue
    
    if marked_count > 0:
        log.info(
            "event=assemble.monitor.stuck_episodes_marked count=%d",
            marked_count
        )
    
    return marked_count


def handle_worker_endpoint_error(
    session: Session,
    episode_id: UUID,
    http_status: int,
    error_message: str,
) -> None:
    """Handle errors from worker endpoint (401, 404, 500, etc.) and track failures.
    
    This function:
    1. Tracks consecutive failures in episode metadata
    2. Marks episode as error if max consecutive failures reached
    3. Provides clear error messages based on HTTP status code
    """
    try:
        episode = session.get(Episode, episode_id)
        if not episode:
            log.warning("event=assemble.monitor.episode_not_found episode_id=%s", str(episode_id))
            return
        
        # Get current metadata
        meta = {}
        if getattr(episode, 'meta_json', None):
            try:
                meta = json.loads(episode.meta_json or '{}')
            except Exception:
                meta = {}
        
        # Track failures
        failures = meta.get('worker_failures', [])
        failures.append({
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'http_status': http_status,
            'error': error_message,
        })
        
        # Keep only recent failures (last 10)
        failures = failures[-10:]
        meta['worker_failures'] = failures
        
        # Count consecutive non-2xx failures
        consecutive_failures = 0
        for failure in reversed(failures):
            if failure.get('http_status', 200) < 200 or failure.get('http_status', 200) >= 300:
                consecutive_failures += 1
            else:
                break
        
        # Determine error message based on HTTP status
        if http_status == 401:
            error_msg = "Worker endpoint authentication failed. Please check TASKS_AUTH configuration."
        elif http_status == 404:
            error_msg = "Worker endpoint not found. Please check WORKER_URL_BASE configuration."
        elif http_status >= 500:
            error_msg = f"Worker endpoint returned server error (HTTP {http_status}). The worker service may be experiencing issues."
        else:
            error_msg = f"Worker endpoint returned error (HTTP {http_status}): {error_message}"
        
        # Mark as error if max consecutive failures reached
        if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            _mark_episode_worker_error(
                session,
                episode,
                "worker_endpoint_failures",
                f"Worker endpoint failed {consecutive_failures} consecutive times. {error_msg}",
                {
                    "consecutive_failures": consecutive_failures,
                    "last_http_status": http_status,
                    "failures": failures[-MAX_CONSECUTIVE_FAILURES:],
                }
            )
        else:
            # Update metadata but don't mark as error yet
            episode.meta_json = json.dumps(meta)
            session.add(episode)
            session.commit()
            
            log.warning(
                "event=assemble.monitor.worker_failure_tracked episode_id=%s http_status=%d consecutive=%d/%d",
                str(episode_id), http_status, consecutive_failures, MAX_CONSECUTIVE_FAILURES
            )
    
    except Exception as e:
        log.error(
            "event=assemble.monitor.handle_worker_error_failed episode_id=%s error=%s",
            str(episode_id), str(e),
            exc_info=True
        )
        session.rollback()

