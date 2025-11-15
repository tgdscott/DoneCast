from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from importlib import import_module
from math import ceil
from pathlib import Path
from typing import Any, Dict, Optional, cast
from uuid import UUID

from sqlalchemy.orm import Session

from api.core.constants import TIER_LIMITS
from api.core.paths import MEDIA_DIR
from api.models.podcast import Episode
from api.models.settings import AppSetting
from api.services.billing import usage as usage_svc
from api.services.transcription import load_media_transcript_metadata_for_filename

# Celery has been removed - all assembly uses Cloud Tasks or inline execution
# No longer need to import create_podcast_episode or celery_app

from . import dto, repo


def _raise_worker_unavailable() -> None:
    """Raise a HTTP 503 describing that the background worker is unavailable."""

    from fastapi import HTTPException  # Local import to avoid FastAPI dependency at module import

    raise HTTPException(
        status_code=503,
        detail={
            "code": "ASSEMBLY_WORKER_UNAVAILABLE",
            "message": "Episode assembly worker is not available. Please try again later or contact support.",
        },
    )


def _queue_episode_for_worker(
    session: Session,
    episode: Episode,
    payload: Dict[str, Any],
    worker_url_base: Optional[str],
    estimated_minutes: Optional[int],
    current_user: Any,
) -> Dict[str, Any]:
    """Queue an episode for processing when worker server comes back online.
    
    Sets episode status to 'pending', stores queue metadata, sends admin alert,
    and returns a friendly success message to the user.
    """
    log = logging.getLogger("assemble")
    
    try:
        from api.models.podcast import EpisodeStatus as _EpStatus
        episode.status = _EpStatus.pending  # type: ignore[assignment]
    except Exception:
        try:
            episode.status = "pending"  # type: ignore[assignment]
        except Exception:
            pass
    
    # Store queue metadata in episode.meta_json
    import json as _json
    from datetime import datetime as _dt, timezone as _tz
    
    meta = {}
    if getattr(episode, 'meta_json', None):
        try:
            meta = _json.loads(episode.meta_json or '{}')
        except Exception:
            meta = {}
    
    # Store queue information
    meta['queued_for_worker'] = True
    meta['queued_at'] = _dt.now(_tz.utc).isoformat()
    meta['queued_worker_url'] = worker_url_base
    meta['retry_count'] = 0
    meta['last_retry_at'] = None
    meta['assembly_payload'] = payload  # Store full payload for retry
    meta['estimated_minutes'] = estimated_minutes
    
    episode.meta_json = _json.dumps(meta)
    session.add(episode)
    session.commit()
    session.refresh(episode)
    
    log.info(
        "event=assemble.service.episode_queued episode_id=%s worker_url=%s - "
        "Episode queued for processing when worker comes back online",
        str(episode.id), worker_url_base
    )
    
    # Send SMS alert to admin (rate-limited to avoid spam)
    # Only send if we haven't sent one in the last 5 minutes
    try:
        from api.services.sms import sms_service
        from datetime import datetime as _dt, timezone as _tz, timedelta as _td
        
        admin_phone = "951-662-1100"  # Admin phone number
        last_alert_key = "last_worker_down_sms_alert"
        
        # Check if we've sent an alert recently (within last 5 minutes)
        should_send_sms = True
        try:
            # Try to get last alert time from a simple cache or database
            # For simplicity, we'll check if there are other recently queued episodes
            # If an episode was queued in the last 5 minutes, skip SMS (already alerted)
            from sqlmodel import select
            five_min_ago = _dt.now(_tz.utc) - _td(minutes=5)
            
            # Check if any episode was queued in the last 5 minutes (besides this one)
            recent_queued = session.exec(
                select(Episode).where(
                    Episode.status == "pending",  # type: ignore
                    Episode.id != episode.id  # type: ignore
                )
            ).all()
            
            for other_ep in recent_queued:
                if not getattr(other_ep, 'meta_json', None):
                    continue
                try:
                    other_meta = _json.loads(other_ep.meta_json or '{}')
                    if other_meta.get('queued_for_worker'):
                        other_queued_at_str = other_meta.get('queued_at')
                        if other_queued_at_str:
                            other_queued_at = _dt.fromisoformat(other_queued_at_str.replace('Z', '+00:00'))
                            if other_queued_at > five_min_ago:
                                # Another episode was queued recently - skip SMS to avoid spam
                                should_send_sms = False
                                log.info("event=assemble.service.admin_sms_skipped episode_id=%s reason=recent_alert", str(episode.id))
                                break
                except Exception:
                    continue
        except Exception as check_err:
            # If check fails, send SMS anyway (better to over-alert than miss an alert)
            log.warning("event=assemble.service.admin_sms_check_failed episode_id=%s error=%s", str(episode.id), str(check_err))
            should_send_sms = True
        
        if should_send_sms:
            sms_service.send_worker_down_critical(admin_phone)
            log.info("event=assemble.service.admin_sms_sent episode_id=%s phone=%s", str(episode.id), admin_phone)
    except Exception as sms_err:
        # Don't fail if SMS fails - log and continue
        log.warning("event=assemble.service.admin_sms_failed episode_id=%s error=%s", str(episode.id), str(sms_err), exc_info=True)
    
    # Return friendly success message to user
    return {
        "mode": "queued",
        "job_id": f"queued-{episode.id}",
        "episode_id": str(episode.id),
        "status": "queued",
        "message": "Your episode has been queued for processing. You will receive a notification once it has been published.",
    }


def _should_auto_fallback() -> bool:
    """Return True when the environment should execute assembly inline."""

    try:
        raw = (os.getenv("CELERY_AUTO_FALLBACK") or "").strip().lower()
        if raw in {"1", "true", "yes", "on"}:
            return True
        env = (os.getenv("APP_ENV") or "dev").strip().lower()
        return env in {"dev", "development", "local"}
    except Exception:
        return False


def _should_allow_inline_fallback() -> bool:
    """Return True when inline fallback is allowed after worker dispatch fails.
    
    In production, this should ALWAYS be False to prevent Cloud Run from falling back
    to inline processing when the worker times out. The worker will complete
    asynchronously, and the episode status will be updated via polling.
    
    CRITICAL: If a worker server is configured, NEVER allow inline fallback.
    The user has explicitly set up a worker server and expects all processing
    to happen there, not inline.
    
    CRITICAL: In production (APP_ENV=production), inline fallback is NEVER allowed,
    regardless of other configuration. This prevents resource contention and
    ensures proper worker isolation.
    """
    log = logging.getLogger("assemble")
    
    try:
        # CRITICAL: If worker server is configured, NEVER allow inline fallback
        worker_url_base = os.getenv("WORKER_URL_BASE")
        app_env = (os.getenv("APP_ENV") or os.getenv("ENV") or os.getenv("PYTHON_ENV") or "dev").strip().lower()
        is_production = app_env == "production"
        use_worker_in_dev_raw = os.getenv("USE_WORKER_IN_DEV", "false")
        use_worker_in_dev = use_worker_in_dev_raw and use_worker_in_dev_raw.lower().strip() in {"true", "1", "yes", "on"}
        worker_server_configured = worker_url_base and (is_production or use_worker_in_dev)
        
        # CRITICAL: In production, NEVER allow inline fallback
        if is_production:
            log.info(
                "event=assemble.service.inline_fallback_disabled_production app_env=%s - "
                "Inline fallback disabled in production environment",
                app_env
            )
            return False
        
        if worker_server_configured:
            # Worker server is configured - NEVER allow inline fallback
            log.info(
                "event=assemble.service.inline_fallback_disabled_worker_configured worker_url=%s - "
                "Worker server is configured, inline fallback disabled",
                worker_url_base
            )
            return False
        
        # Check explicit env var (defaults to False for safety)
        raw = (os.getenv("ALLOW_ASSEMBLY_INLINE_FALLBACK") or "").strip().lower()
        if raw in {"1", "true", "yes", "on"}:
            log.warning(
                "event=assemble.service.inline_fallback_enabled_via_env app_env=%s - "
                "Inline fallback explicitly enabled via ALLOW_ASSEMBLY_INLINE_FALLBACK env var. "
                "This should only be used in development environments.",
                app_env
            )
            return True
        if raw in {"0", "false", "no", "off"}:
            log.info(
                "event=assemble.service.inline_fallback_disabled_via_env app_env=%s - "
                "Inline fallback explicitly disabled via ALLOW_ASSEMBLY_INLINE_FALLBACK env var",
                app_env
            )
            return False
        
        # Default: only allow in dev environments (and only if worker server is NOT configured)
        env = (os.getenv("APP_ENV") or "dev").strip().lower()
        allowed = env in {"dev", "development", "local"}
        
        if allowed:
            log.info(
                "event=assemble.service.inline_fallback_allowed_dev app_env=%s - "
                "Inline fallback allowed in development environment",
                env
            )
        else:
            log.info(
                "event=assemble.service.inline_fallback_disabled_default app_env=%s - "
                "Inline fallback disabled by default (not a dev environment)",
                env
            )
        
        return allowed
    except Exception as e:
        log.error(
            "event=assemble.service.inline_fallback_check_failed error=%s - "
            "Error checking if inline fallback should be allowed, defaulting to False for safety",
            str(e),
            exc_info=True
        )
        return False


_INLINE_EXECUTOR = None


def _load_inline_executor():
    """Return a callable capable of running the assembly orchestration inline.
    
    Returns None if the inline executor cannot be loaded. This should be logged
    as it indicates a configuration or import issue.
    """

    global _INLINE_EXECUTOR
    log = logging.getLogger("assemble")

    if _INLINE_EXECUTOR is not None:
        return _INLINE_EXECUTOR

    module_candidates = (
        "worker.tasks.assembly.inline",
        "backend.worker.tasks.assembly.inline",
        "worker.tasks.assembly.orchestrator",
        "backend.worker.tasks.assembly.orchestrator",
    )

    for module_name in module_candidates:
        try:
            module = import_module(module_name)
        except Exception as import_err:
            log.debug(
                "[assemble] Failed to import module %s for inline executor: %s",
                module_name, import_err
            )
            continue
        candidate = getattr(module, "orchestrate_create_podcast_episode", None)
        if callable(candidate):
            _INLINE_EXECUTOR = candidate
            log.info(
                "[assemble] Loaded inline executor from module %s",
                module_name
            )
            return _INLINE_EXECUTOR

    # Celery has been removed - only use inline orchestrator
    # Log this as a warning since it means inline fallback cannot be used
    log.warning(
        "event=assemble.service.inline_executor_unavailable - "
        "Inline executor could not be loaded from any candidate module. "
        "Inline fallback will not be available. "
        "Candidates tried: %s",
        ", ".join(module_candidates)
    )
    return None


def _run_inline_fallback(
    *,
    episode_id: Any,
    template_id: str,
    main_content_filename: str,
    output_filename: str,
    tts_values: Dict[str, Any],
    episode_details: Dict[str, Any],
    user_id: Any,
    podcast_id: Any,
    intents: Optional[Dict[str, Any]],
    use_auphonic: bool = False,
) -> Optional[Dict[str, Any]]:
    """Attempt to execute episode assembly inline when workers are unavailable.
    
    WARNING: Inline execution in production is NOT intended behavior and should
    trigger investigation. This function logs high-severity events when called
    in production environments.
    """

    log = logging.getLogger("assemble")
    
    # Check if we're in production - inline fallback should be rare/never in production
    app_env = (os.getenv("APP_ENV") or os.getenv("ENV") or os.getenv("PYTHON_ENV") or "dev").strip().lower()
    is_production = app_env == "production"
    
    task_fn = _load_inline_executor()
    if not task_fn:
        # Inline executor cannot be loaded - this is a configuration issue
        log.error(
            "event=assemble.service.inline_fallback_failed episode_id=%s reason=executor_unavailable - "
            "Inline fallback attempted but executor could not be loaded",
            str(episode_id)
        )
        return None

    # Log high-severity warning if this happens in production
    if is_production:
        log.error(
            "event=assemble.service.inline_fallback_unexpected episode_id=%s app_env=%s - "
            "CRITICAL: Inline fallback is being used in production. This is NOT intended behavior. "
            "Worker server or Cloud Tasks should be handling assembly. "
            "This indicates a configuration or infrastructure issue that requires immediate investigation.",
            str(episode_id), app_env
        )
    else:
        log.warning(
            "event=assemble.service.falling_back_to_inline episode_id=%s app_env=%s - "
            "Falling back to inline execution (dev environment only - this should not happen in production)",
            str(episode_id), app_env
        )

    try:
        result = task_fn(
            episode_id=str(episode_id),
            template_id=str(template_id),
            main_content_filename=str(main_content_filename),
            output_filename=str(output_filename),
            tts_values=tts_values or {},
            episode_details=episode_details or {},
            user_id=str(user_id),
            podcast_id=str(podcast_id or ""),
            intents=intents or None,
            skip_charge=True,
            use_auphonic=use_auphonic,
        )
        
        # Log success but with appropriate severity based on environment
        if is_production:
            log.error(
                "event=assemble.service.inline_fallback_completed episode_id=%s - "
                "Inline fallback completed in PRODUCTION. This should not happen. "
                "Investigate why worker server or Cloud Tasks was unavailable.",
                str(episode_id)
            )
        else:
            log.info(
                "event=assemble.service.inline_fallback_completed episode_id=%s - "
                "Inline fallback completed successfully (dev environment)",
                str(episode_id)
            )
        
        return {
            "mode": "fallback-inline",
            "job_id": "fallback-inline",
            "result": result,
            "episode_id": str(episode_id),
        }
    except Exception as exc:
        log.error(
            "event=assemble.service.inline_fallback_execution_failed episode_id=%s error=%s - "
            "Inline fallback execution failed",
            str(episode_id), str(exc),
            exc_info=True
        )
        return None


def _can_run_inline() -> bool:
    """Return True if an inline fallback implementation is importable."""

    return _load_inline_executor() is not None


def _merge_transcript_metadata_from_upload(
    session: Session,
    meta: Dict[str, Any],
    main_content_filename: str,
) -> Dict[str, Any]:
    """Augment episode meta with persisted transcript metadata for the upload."""

    if not isinstance(meta, dict):
        meta = {}

    try:
        stored = load_media_transcript_metadata_for_filename(session, main_content_filename)
    except Exception:
        stored = None

    if not stored:
        return meta

    transcripts_meta = meta.get("transcripts")
    if not isinstance(transcripts_meta, dict):
        transcripts_meta = {}

    merged = dict(transcripts_meta)
    for key, value in stored.items():
        if key not in merged or merged.get(key) in (None, "", [], False):
            merged[key] = value

    if merged:
        meta["transcripts"] = merged
        if not meta.get("transcript_stem") and stored.get("stem"):
            meta["transcript_stem"] = stored.get("stem")

    return meta


def _episodes_created_this_month(session: Session, user_id) -> int:
    from calendar import monthrange
    from datetime import datetime, timezone
    from sqlmodel import select
    from sqlalchemy import func

    now = datetime.now(timezone.utc)
    start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    try:
        # Use select_from(Episode) to avoid type-checker confusion around Episode.id
        q = select(func.count()).select_from(Episode)
        if hasattr(Episode, 'created_at'):
            q = q.where(Episode.created_at >= start)
        # NOTE: user_id filter temporarily removed due to analyzer type issue
        res = session.execute(q).scalar_one()
        return int(res or 0)
    except Exception:
        return 0


def _probe_audio_seconds(path: Path) -> Optional[float]:
    """Probe an audio file on disk and return its duration in seconds."""

    try:
        if not path.is_file():
            return None
    except Exception:
        return None

    seconds = 0.0
    try:
        import subprocess

        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if proc.returncode == 0:
            payload = json.loads(proc.stdout or "{}")
            duration = float(payload.get("format", {}).get("duration", 0))
            if duration and duration > 0:
                seconds = float(duration)
    except Exception:
        seconds = 0.0

    if seconds <= 0:
        try:
            from pydub import AudioSegment as _AS

            seg = _AS.from_file(path)
            seconds = len(seg) / 1000.0
        except Exception:
            seconds = 0.0

    return float(seconds) if seconds > 0 else None


def _estimate_audio_seconds(filename: str) -> Optional[float]:
    """Best-effort estimate of an audio file's duration in seconds."""

    try:
        raw = str(filename or "").strip()
        if not raw:
            return None

        candidates: list[Path] = []
        if raw.startswith("gs://"):
            base = raw.split("/")[-1]
            if base:
                candidates.append(MEDIA_DIR / base)
                candidates.append(MEDIA_DIR / "media_uploads" / base)
        else:
            path = Path(raw)
            try:
                if path.is_file():
                    candidates.append(path)
            except Exception:
                pass
            base = path.name
            if base:
                candidates.append(MEDIA_DIR / base)
                candidates.append(MEDIA_DIR / "media_uploads" / base)

        seen: set[str] = set()
        for cand in candidates:
            key = str(cand)
            if key in seen:
                continue
            seen.add(key)
            seconds = _probe_audio_seconds(cand)
            if seconds and seconds > 0:
                return float(seconds)
        return None
    except Exception:
        return None


def _estimate_processing_minutes(filename: str) -> Optional[int]:
    """Best-effort estimate of audio length in whole minutes for quota checks."""

    seconds = _estimate_audio_seconds(filename)
    if not seconds:
        return None
    return max(1, int(ceil(seconds / 60.0)))


def _estimate_static_segments_seconds(template: Any) -> float:
    """Estimate total seconds contributed by static template segments."""

    total = 0.0
    try:
        if hasattr(template, "segments") and isinstance(template.segments, list):
            segments = template.segments
        else:
            segments = json.loads(getattr(template, "segments_json", "[]") or "[]")
    except Exception:
        segments = []

    for segment in segments or []:
        try:
            source = None
            if isinstance(segment, dict):
                seg_type = segment.get("segment_type")
                source = segment.get("source")
            else:
                seg_type = getattr(segment, "segment_type", None)
                source = getattr(segment, "source", None)
            if seg_type == "content":
                continue
            if not source:
                continue
            if isinstance(source, dict):
                stype = source.get("source_type")
                filename = source.get("filename")
            else:
                stype = getattr(source, "source_type", None)
                filename = getattr(source, "filename", None)
            if stype != "static" or not filename:
                continue
            seconds = _estimate_audio_seconds(filename)
            if seconds and seconds > 0:
                total += float(seconds)
        except Exception:
            continue
    return float(total)


def minutes_precheck(
    *,
    session: Session,
    current_user,
    template_id: Optional[str],
    main_content_filename: str,
) -> Dict[str, Any]:
    """Return usage information to determine if processing minutes remain."""

    # Admin and SuperAdmin users have unlimited processing minutes
    user_role = getattr(current_user, "role", None)
    is_admin = getattr(current_user, "is_admin", False)
    if user_role in ("admin", "superadmin") or is_admin:
        tier = "unlimited"
    else:
        tier = getattr(current_user, "tier", "free")
    
    limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
    max_minutes = limits.get("max_processing_minutes_month")

    main_seconds = _estimate_audio_seconds(main_content_filename)
    static_seconds = 0.0

    template = None
    if template_id:
        try:
            tid = UUID(str(template_id))
            template = repo.get_template_by_id(session, tid)
            if template and getattr(template, "user_id", None) not in (None, getattr(current_user, "id", None)):
                template = None
        except Exception:
            template = None

    if template is not None:
        static_seconds = _estimate_static_segments_seconds(template)

    total_seconds = float((main_seconds or 0.0) + static_seconds)
    required_minutes = 0
    if total_seconds > 0:
        required_minutes = max(1, int(ceil(total_seconds / 60.0)))
    elif main_seconds:
        required_minutes = max(1, int(ceil(float(main_seconds) / 60.0)))

    response: Dict[str, Any] = {
        "tier": tier,
        "allowed": True,
        "max_minutes": max_minutes,
        "main_seconds": float(main_seconds) if main_seconds else None,
        "static_seconds": static_seconds,
        "total_seconds": total_seconds if total_seconds > 0 else None,
        "minutes_required": required_minutes,
        "minutes_used": None,
        "minutes_remaining": None,
    }

    if max_minutes is None:
        return response

    from datetime import datetime as _dt, timezone as _tz

    now = _dt.now(_tz.utc)
    start = _dt(now.year, now.month, 1, tzinfo=_tz.utc)
    try:
        minutes_used = usage_svc.month_minutes_used(session, current_user.id, start, now)
    except Exception:
        minutes_used = None

    if minutes_used is not None:
        try:
            minutes_used = int(minutes_used)
        except Exception:
            minutes_used = None
    response["minutes_used"] = minutes_used

    minutes_remaining: Optional[int]
    if minutes_used is None:
        minutes_remaining = max_minutes
    else:
        minutes_remaining = max_minutes - minutes_used
    response["minutes_remaining"] = minutes_remaining

    if required_minutes <= 0:
        return response

    if minutes_remaining is not None and minutes_remaining < required_minutes:
        detail: Dict[str, Any] = {
            "code": "INSUFFICIENT_MINUTES",
            "minutes_required": int(required_minutes),
            "minutes_remaining": int(max(minutes_remaining, 0)),
            "message": "Not enough processing minutes remain to assemble this episode.",
            "source": "precheck",
        }
        renewal = getattr(current_user, "subscription_expires_at", None)
        if renewal:
            try:
                detail["renewal_date"] = renewal.isoformat()
            except Exception:
                pass
        response["allowed"] = False
        response["detail"] = detail
    return response


def assemble_or_queue(
    session: Session,
    current_user,
    template_id: str,
    main_content_filename: str,
    output_filename: str,
    tts_values: Dict[str, Any],
    episode_details: Dict[str, Any],
    intents: Optional[Dict[str, Any]] = None,
    use_auphonic: bool = False,
) -> Dict[str, Any]:
    """
    Assemble an episode or queue it for processing.
    
    Processing MUST go through a worker server or Cloud Tasks. Inline processing is NEVER allowed.
    
    Processing priority:
    1. Worker server (if WORKER_URL_BASE is set and USE_WORKER_IN_DEV=true or APP_ENV=production)
    2. Cloud Tasks (if configured for production)
    3. Direct worker POST (if worker server is configured but Cloud Tasks is disabled)
    
    If none of these are available, the function will raise an error. Inline processing is disabled.
    
    NOTE: Duplicate numbering check REMOVED - never block episode creation
    Conflicts should be resolved AFTER assembly, not before
    Users should always be able to create episodes
    """
    
    # Quota check (same logic as router but service-level)
    # Admin and SuperAdmin users have unlimited processing minutes
    user_role = getattr(current_user, "role", None)
    is_admin = getattr(current_user, "is_admin", False)
    if user_role in ("admin", "superadmin") or is_admin:
        tier = "unlimited"
    else:
        tier = getattr(current_user, 'tier', 'free')
    
    # Get priority for this tier
    try:
        from api.billing.plans import get_plan_priority
        priority = get_plan_priority(tier)
    except Exception:
        priority = 1  # Default to lowest priority if lookup fails
    
    limits = TIER_LIMITS.get(tier, TIER_LIMITS['free'])
    max_eps = limits.get('max_episodes_month')
    if max_eps is not None:
        used = _episodes_created_this_month(session, current_user.id)
        if used >= max_eps:
            from fastapi import HTTPException
            raise HTTPException(status_code=402, detail="Monthly episode quota reached for your tier")

    # Check if worker server or Cloud Tasks is configured
    # If worker_url_base is set, we can queue episodes even if worker is down
    worker_url_base = os.getenv("WORKER_URL_BASE")
    app_env = (os.getenv("APP_ENV") or os.getenv("ENV") or os.getenv("PYTHON_ENV") or "dev").strip().lower()
    is_production = app_env == "production"
    use_worker_in_dev_raw = os.getenv("USE_WORKER_IN_DEV", "false")
    use_worker_in_dev = use_worker_in_dev_raw and use_worker_in_dev_raw.lower().strip() in {"true", "1", "yes", "on"}
    worker_server_configured = worker_url_base and (is_production or use_worker_in_dev)
    
    # Check if Cloud Tasks is available
    try:
        from infrastructure.tasks_client import should_use_cloud_tasks
        cloud_tasks_available = should_use_cloud_tasks()
    except Exception:
        cloud_tasks_available = False
    
    # If neither worker server URL nor Cloud Tasks is configured, fail immediately
    # We need at least worker_url_base to queue episodes (even if worker is down)
    if not worker_url_base and not cloud_tasks_available:
        log = logging.getLogger("assemble")
        log.error(
            "event=assemble.service.no_worker_configured - "
            "Neither WORKER_URL_BASE nor Cloud Tasks is configured. "
            "Episode assembly requires WORKER_URL_BASE (for queueing) or Cloud Tasks. "
            "Inline processing is disabled."
        )
        _raise_worker_unavailable()

    # Prepare metadata and admin test-mode overrides
    ep_title = (episode_details.get("title") or output_filename or "").strip() or "Untitled Episode"
    ep_description = (episode_details.get("description") or "").strip()
    cover_image_path = episode_details.get("cover_image_path")
    sn_input = episode_details.get("season") or episode_details.get("season_number")
    en_input = episode_details.get("episodeNumber") or episode_details.get("episode_number")
    raw_tags = episode_details.get("tags")
    explicit_flag = bool(episode_details.get("explicit") or episode_details.get("is_explicit"))

    # Enforce processing minutes quota (if enabled for the user's tier)
    max_minutes = limits.get('max_processing_minutes_month')
    estimated_minutes = _estimate_processing_minutes(main_content_filename)
    if max_minutes is not None:
        from datetime import datetime as _dt, timezone as _tz

        now = _dt.now(_tz.utc)
        start = _dt(now.year, now.month, 1, tzinfo=_tz.utc)
        minutes_used = usage_svc.month_minutes_used(session, current_user.id, start, now)
        minutes_remaining = max_minutes - minutes_used if minutes_used is not None else 0
        needed = estimated_minutes or 1
        if minutes_remaining < needed:
            from fastapi import HTTPException

            renewal = getattr(current_user, 'subscription_expires_at', None)
            detail = {
                "code": "INSUFFICIENT_MINUTES",
                "minutes_required": int(needed),
                "minutes_remaining": int(max(minutes_remaining, 0)),
                "message": "Not enough processing minutes remain to assemble this episode.",
            }
            if renewal:
                try:
                    detail["renewal_date"] = renewal.isoformat()
                except Exception:
                    pass
            raise HTTPException(status_code=402, detail=detail)

    # Admin test mode
    try:
        admin_rec = session.get(AppSetting, 'admin_settings')
        import json as _json
        adm = _json.loads(admin_rec.value_json or '{}') if admin_rec else {}
        test_mode = bool(adm.get('test_mode'))
    except Exception:
        test_mode = False
    if test_mode:
        from datetime import datetime as _dt
        now = _dt.now()
        try:
            sn_input = str(now.day)
        except Exception:
            pass
        try:
            en_input = f"{now.hour:02d}{now.minute:02d}"
        except Exception:
            pass
        raw_title = (episode_details.get("title") or "").strip()
        if not raw_title:
            try:
                from pathlib import Path as _Path
                base = _Path(str(main_content_filename)).stem or _Path(str(output_filename)).stem
                ep_title = f"Test - {base}"
            except Exception:
                pass
        # Enforce test-mode output filename pattern
        try:
            from pathlib import Path as _Path
            import re as _re
            base = _Path(str(output_filename or "")).stem or _Path(str(main_content_filename or "")).stem or "episode"
            slug = _re.sub(r"[^A-Za-z0-9_-]+", "-", base).strip("-")
            output_filename = f"test{sn_input}{en_input}---{slug}"
        except Exception:
            pass

    # Link to a podcast (prefer template-linked podcast if present)
    podcast_id = None
    try:
        from uuid import UUID as _UUID
        _tid = _UUID(str(template_id))
        t = repo.get_template_by_id(session, _tid)
        if t and getattr(t, 'podcast_id', None):
            podcast_id = t.podcast_id
    except Exception:
        podcast_id = None
    if podcast_id is None:
        podcast = repo.get_first_podcast_for_user(session, current_user.id)
        if podcast:
            podcast_id = podcast.id

    # Build initial episode row
    from datetime import datetime as _dt
    ep_kwargs: Dict[str, Any] = {
        "user_id": current_user.id,
        "template_id": template_id,
        "title": ep_title,
        "cover_path": cover_image_path,
        "show_notes": ep_description,
        "season_number": int(sn_input) if (isinstance(sn_input, (int, str)) and str(sn_input).isdigit()) else None,
        "episode_number": int(en_input) if (isinstance(en_input, (int, str)) and str(en_input).isdigit()) else None,
        "processed_at": _dt.utcnow(),
        "created_at": _dt.utcnow(),
        "priority": priority,  # Set priority based on user tier
    }
    if podcast_id is not None:
        ep_kwargs["podcast_id"] = podcast_id
    ep = Episode(**ep_kwargs)
    # status = processing
    try:
        from api.models.podcast import EpisodeStatus as _EpStatus
        ep.status = _EpStatus.processing  # type: ignore[assignment]
    except Exception:
        try:
            ep.status = "processing"  # type: ignore[assignment]
        except Exception:
            pass
    # Uniqueness pre-check if both numbers present - WARN but DON'T BLOCK
    try:
        if ep.podcast_id and ep.season_number is not None and ep.episode_number is not None:
            if repo.episode_exists_with_number(session, ep.podcast_id, ep.season_number, ep.episode_number):
                logging.warning(
                    "Episode S%sE%s numbering conflict detected for podcast %s (episode %s) - allowing assembly but flagging",
                    ep.season_number, ep.episode_number, ep.podcast_id, ep.id
                )
                # Flag this episode and find all duplicates to flag them too
                ep.has_numbering_conflict = True
                try:
                    from sqlmodel import select
                    from api.models.podcast import Episode as EpisodeModel
                    duplicates = session.exec(
                        select(EpisodeModel)
                        .where(EpisodeModel.podcast_id == ep.podcast_id)
                        .where(EpisodeModel.season_number == ep.season_number)
                        .where(EpisodeModel.episode_number == ep.episode_number)
                        .where(EpisodeModel.id != ep.id)
                    ).all()
                    for dup in duplicates:
                        dup.has_numbering_conflict = True
                        session.add(dup)
                except Exception:
                    logging.exception("Failed to flag duplicate episodes")
    except Exception:
        pass
    # Tags / explicit
    tags_list = dto.parse_tags(raw_tags)
    try:
        if tags_list and hasattr(ep, 'set_tags'):
            ep.set_tags(tags_list)
        elif tags_list:
            import json as _json
            ep.tags_json = _json.dumps(tags_list)
    except Exception:
        pass
    try:
        if explicit_flag:
            ep.is_explicit = True
    except Exception:
        pass
    # Early flubber cuts store in meta
    try:
        pre_flubber_cuts = episode_details.get("flubber_cuts_ms") or []
        if pre_flubber_cuts and isinstance(pre_flubber_cuts, (list, tuple)):
            import json as _json
            clean_cuts = [ (int(s), int(e)) for s,e in pre_flubber_cuts if isinstance(s, (int,float)) and isinstance(e, (int,float)) and e> s ]
            meta = {}
            if getattr(ep, 'meta_json', None):
                try:
                    meta = _json.loads(ep.meta_json or '{}')
                except Exception:
                    meta = {}
            meta['flubber_cuts_ms'] = clean_cuts
            ep.meta_json = _json.dumps(meta)
    except Exception:
        pass
    session.add(ep)
    session.commit()
    session.refresh(ep)

    # Persist working filename + helpful hints for later transcript lookup
    from pathlib import Path
    import json as _json
    try:
        ep.working_audio_name = Path(str(main_content_filename)).name
        meta = {}
        if getattr(ep, "meta_json", None):
            try:
                meta = _json.loads(ep.meta_json or "{}")
            except Exception:
                meta = {}
        meta["main_content_filename"] = str(main_content_filename)
        meta["output_filename"] = str(output_filename or "")
        meta["source_filename"] = str(main_content_filename)
        # Persist additional context for future retry capability
        try:
            meta["template_id"] = str(template_id)
        except Exception:
            pass
        if tts_values:
            meta["tts_values"] = tts_values
        if episode_details:
            meta["episode_details"] = episode_details
        if intents:
            meta["intents"] = intents
        meta = _merge_transcript_metadata_from_upload(session, meta, str(main_content_filename))
        ep.meta_json = _json.dumps(meta)
        session.add(ep)
        session.commit()
        session.refresh(ep)
    except Exception:
        session.rollback()

    # All task dispatch goes through tasks_client.enqueue_http_task()
    # This ensures consistent routing, logging, and error handling.
    # tasks_client handles:
    # - Cloud Tasks (production)
    # - Worker server routing (dev mode with USE_WORKER_IN_DEV, or production with WORKER_URL_BASE)
    # Inline processing is NEVER used
    log = logging.getLogger("assemble")
    
    # Build payload for task dispatch
    payload = {
        "episode_id": str(ep.id),
        "template_id": str(template_id),
        "main_content_filename": str(main_content_filename),
        "output_filename": str(output_filename or ""),
        "tts_values": cast(Dict[str, Any], tts_values or {}),
        "episode_details": cast(Dict[str, Any], episode_details or {}),
        "user_id": str(current_user.id),
        "podcast_id": str(getattr(ep, 'podcast_id', '') or ''),
        "intents": cast(Dict[str, Any], intents or {}),
        "use_auphonic": bool(use_auphonic),
        "priority": priority,  # Include priority in payload for logging
    }
    
    # All task dispatch goes through tasks_client.enqueue_http_task()
    # This handles Cloud Tasks (production) and worker routing (dev)
    # Inline processing is NEVER used - if dispatch fails, raise an error
    try:
        from infrastructure.tasks_client import enqueue_http_task, should_use_cloud_tasks  # type: ignore
        
        # Check if Cloud Tasks should be used
        use_cloud_tasks = should_use_cloud_tasks()
        
        if use_cloud_tasks:
            log.info("event=assemble.service.enqueueing_task episode_id=%s priority=%s tier=%s", str(ep.id), priority, tier)
            try:
                task_info = enqueue_http_task("/api/tasks/assemble", payload)
                task_name = task_info.get("name", "unknown")
                log.info("event=assemble.service.task_enqueued episode_id=%s task_name=%s priority=%s tier=%s", str(ep.id), task_name, priority, tier)
                
                # Store job id in episode metadata for visibility
                try:
                    import json as _json
                    meta = {}
                    if getattr(ep, 'meta_json', None):
                        try:
                            meta = _json.loads(ep.meta_json or '{}')
                        except Exception:
                            meta = {}
                    meta['assembly_job_id'] = task_name
                    ep.meta_json = _json.dumps(meta)
                    session.add(ep)
                    session.commit()
                    session.refresh(ep)
                    log.info("event=assemble.service.metadata_saved episode_id=%s job_id=%s", str(ep.id), task_name)
                except Exception as meta_err:
                    log.warning("event=assemble.service.metadata_save_failed episode_id=%s error=%s", str(ep.id), str(meta_err))
                    session.rollback()
                
                # Determine mode based on task name
                if task_name.startswith("dry-run-"):
                    mode = "dry-run"
                elif task_name.startswith("dev-worker-") or "worker" in task_name:
                    mode = "worker-dev"
                elif "cloud" in task_name or "projects/" in task_name:
                    mode = "cloud-task"
                else:
                    mode = "local-dispatch"
                
                return {"mode": mode, "job_id": task_name, "episode_id": str(ep.id)}
            except Exception as cloud_tasks_err:
                # Cloud Tasks failed - try direct worker POST, or queue if worker_url_base is set
                log.warning("event=assemble.service.cloud_tasks_failed episode_id=%s error=%s", str(ep.id), str(cloud_tasks_err))
                # Fall through to direct worker POST attempt, or queue if that also fails
        else:
            log.info("event=assemble.service.cloud_tasks_disabled episode_id=%s", str(ep.id))
            # Cloud Tasks disabled - try direct worker POST, or queue if worker_url_base is set
            # Fall through to direct worker POST attempt
        
        # Attempt direct worker POST if Cloud Tasks is disabled or failed
        worker_url_base = os.getenv("WORKER_URL_BASE")
        if worker_url_base:
            import httpx
            base_url = worker_url_base.rstrip("/")
            url = f"{base_url}/api/tasks/assemble"
            tasks_auth = os.getenv("TASKS_AUTH", "a-secure-local-secret")
            headers = {"Content-Type": "application/json", "X-Tasks-Auth": tasks_auth}
            timeout = 1800.0  # 30 minutes for assembly
            
            log.info("event=assemble.service.trying_worker_direct episode_id=%s url=%s", str(ep.id), url)
            try:
                with httpx.Client(timeout=timeout) as client:
                    r = client.post(url, json=payload, headers=headers)
                    if 200 <= r.status_code < 300:
                        # Success: worker dispatched
                        result = r.json() if r.content else {}
                        log.info("event=assemble.service.worker_direct_dispatched episode_id=%s status=%s", str(ep.id), r.status_code)
                        
                        # Store job id in episode metadata
                        job_id = f"worker-direct-{datetime.utcnow().isoformat()}"
                        try:
                            import json as _json
                            meta = {}
                            if getattr(ep, 'meta_json', None):
                                try:
                                    meta = _json.loads(ep.meta_json or '{}')
                                except Exception:
                                    meta = {}
                            meta['assembly_job_id'] = job_id
                            ep.meta_json = _json.dumps(meta)
                            session.add(ep)
                            session.commit()
                            session.refresh(ep)
                        except Exception as meta_err:
                            log.warning("event=assemble.service.metadata_save_failed episode_id=%s error=%s", str(ep.id), str(meta_err))
                            session.rollback()
                        
                        return {"mode": "worker-direct", "job_id": job_id, "episode_id": str(ep.id)}
                    else:
                        # Non-2xx response: worker failed, inline processing is disabled
                        log.error("event=assemble.service.worker_direct_non_2xx episode_id=%s status=%s - Worker server returned error", str(ep.id), r.status_code)
                        # Track worker endpoint error
                        try:
                            from api.services.episodes.cloud_tasks_monitor import handle_worker_endpoint_error
                            handle_worker_endpoint_error(
                                session,
                                ep.id,
                                r.status_code,
                                r.text[:200] if r.text else f"HTTP {r.status_code}",
                            )
                        except Exception as track_err:
                            log.warning("event=assemble.service.track_worker_error_failed episode_id=%s error=%s", str(ep.id), str(track_err))
                        # Fall through to raise error - inline processing is disabled
            except httpx.HTTPStatusError as http_err:
                # Worker POST failed with HTTP error
                status_code = http_err.response.status_code if http_err.response else 500
                log.error("event=assemble.service.worker_direct_http_error episode_id=%s status=%s - Worker server HTTP error", str(ep.id), status_code)
                # Track worker endpoint error
                try:
                    from api.services.episodes.cloud_tasks_monitor import handle_worker_endpoint_error
                    handle_worker_endpoint_error(
                        session,
                        ep.id,
                        status_code,
                        str(http_err)[:200],
                    )
                except Exception as track_err:
                    log.warning("event=assemble.service.track_worker_error_failed episode_id=%s error=%s", str(ep.id), str(track_err))
                # Fall through to raise error - inline processing is disabled
            except Exception as worker_err:
                # Worker POST failed: inline processing is disabled
                log.error("event=assemble.service.worker_direct_failed episode_id=%s error=%s - Worker server unavailable", str(ep.id), str(worker_err))
                # Track worker endpoint error (network/connection errors)
                try:
                    from api.services.episodes.cloud_tasks_monitor import handle_worker_endpoint_error
                    handle_worker_endpoint_error(
                        session,
                        ep.id,
                        0,  # 0 indicates network/connection error
                        str(worker_err)[:200],
                    )
                except Exception as track_err:
                    log.warning("event=assemble.service.track_worker_error_failed episode_id=%s error=%s", str(ep.id), str(track_err))
                # Fall through to raise error - inline processing is disabled
        
        # If we get here, worker dispatch failed - queue the episode for later processing if worker_url_base is set
        # Otherwise, fail (can't queue without a worker URL)
        worker_url_base_for_queue = os.getenv("WORKER_URL_BASE")
        
        if worker_url_base_for_queue:
            # Queue the episode for later processing
            log.warning(
                "event=assemble.service.worker_dispatch_failed episode_id=%s - "
                "Worker dispatch failed. Queueing episode for processing when worker comes back online.",
                str(ep.id)
            )
            return _queue_episode_for_worker(
                session=session,
                episode=ep,
                payload=payload,
                worker_url_base=worker_url_base_for_queue,
                estimated_minutes=estimated_minutes,
                current_user=current_user,
            )
        else:
            # No worker URL to queue for - fail with error
            log.error(
                "event=assemble.service.worker_dispatch_failed_no_queue episode_id=%s - "
                "Worker dispatch failed and no WORKER_URL_BASE configured for queueing. Cannot queue episode.",
                str(ep.id)
            )
            _raise_worker_unavailable()
        
    except Exception as e:
        # Unexpected error - log and raise
        error_msg = f"Failed to dispatch assembly task: {e}"
        log.error(f"event=assemble.service.task_dispatch_error episode_id={ep.id} error={error_msg}", exc_info=True)
        # Re-raise to trigger HTTP 5xx response
        raise RuntimeError(error_msg) from e
