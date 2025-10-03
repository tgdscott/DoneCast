from __future__ import annotations

import json
import logging
import os
import time
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

try:  # Optional dependency: Celery worker package is not always installed
    from worker.tasks import create_podcast_episode, celery_app  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - dev/staging environments without Celery
    create_podcast_episode = None  # type: ignore
    celery_app = None  # type: ignore
except Exception:  # pragma: no cover - guard against indirect import errors inside worker.tasks
    # If worker.tasks exists but raises during import (e.g., due to a submodule error),
    # avoid failing this service import so the API can still start and surface a 503 at runtime.
    create_podcast_episode = None  # type: ignore
    celery_app = None  # type: ignore

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
) -> Optional[Dict[str, Any]]:
    """Attempt to execute episode assembly inline when workers are unavailable."""

    try:
        from typing import Any as _Any, cast as _cast

        if create_podcast_episode is not None:
            task_fn = _cast(_Any, create_podcast_episode)
        else:
            from worker.tasks.assembly.orchestrator import (  # type: ignore[import]
                orchestrate_create_podcast_episode,
            )

            task_fn = orchestrate_create_podcast_episode

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
        )
        return {
            "mode": "fallback-inline",
            "job_id": "fallback-inline",
            "result": result,
            "episode_id": str(episode_id),
        }
    except Exception:
        logging.getLogger("assemble").exception(
            "[assemble] Inline fallback execution failed", exc_info=True
        )
        return None


def _can_run_inline() -> bool:
    """Return True if an inline fallback implementation is importable."""

    if create_podcast_episode is not None:
        return True
    try:
        from worker.tasks.assembly.orchestrator import (  # type: ignore[import]
            orchestrate_create_podcast_episode,
        )

        return callable(orchestrate_create_podcast_episode)
    except Exception:
        return False


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
) -> Dict[str, Any]:
    auto_fallback = _should_auto_fallback()

    # Quota check (same logic as router but service-level)
    tier = getattr(current_user, 'tier', 'free')
    limits = TIER_LIMITS.get(tier, TIER_LIMITS['free'])
    max_eps = limits.get('max_episodes_month')
    if max_eps is not None:
        used = _episodes_created_this_month(session, current_user.id)
        if used >= max_eps:
            from fastapi import HTTPException
            raise HTTPException(status_code=402, detail="Monthly episode quota reached for your tier")

    # Ensure the worker task module (or inline fallback) is available before performing DB writes.
    if create_podcast_episode is None:
        if not auto_fallback or not _can_run_inline():
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
    # Uniqueness pre-check if both numbers present
    try:
        if ep.podcast_id and ep.season_number is not None and ep.episode_number is not None:
            if repo.episode_exists_with_number(session, ep.podcast_id, ep.season_number, ep.episode_number):
                from fastapi import HTTPException
                raise HTTPException(status_code=409, detail="Episode numbering already in use for this podcast")
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
        ep.meta_json = _json.dumps(meta)
        session.add(ep)
        session.commit()
        session.refresh(ep)
    except Exception:
        session.rollback()

    # Run inline or queue
    if os.getenv("CELERY_EAGER", "").strip().lower() in {"1","true","yes","on"}:
        # EAGER path: charge immediately using source duration and inline correlation id
        try:
            minutes = estimated_minutes or _estimate_processing_minutes(main_content_filename) or 1
            corr = f"inline:{str(ep.id)}:{int(time.time())}"
            usage_svc.post_debit(
                session=session,
                user_id=current_user.id,
                minutes=minutes,
                episode_id=ep.id,
                reason="PROCESS_AUDIO",
                correlation_id=corr,
                notes="charge at eager start",
            )
        except Exception:
            pass
        inline_result = _run_inline_fallback(
            episode_id=ep.id,
            template_id=template_id,
            main_content_filename=main_content_filename,
            output_filename=output_filename,
            tts_values=tts_values or {},
            episode_details=episode_details or {},
            user_id=getattr(current_user, "id", None),
            podcast_id=getattr(ep, "podcast_id", None),
            intents=intents,
        )
        if inline_result:
            inline_result["mode"] = "eager-inline"
            inline_result["job_id"] = inline_result.get("job_id") or "eager-inline"
            return inline_result
        _raise_worker_unavailable()
    else:
        # Optional: Use Cloud Tasks HTTP dispatch instead of Celery when enabled.
        if os.getenv("USE_CLOUD_TASKS", "").strip().lower() in {"1", "true", "yes", "on"}:
            try:
                from infrastructure.tasks_client import enqueue_http_task, should_use_cloud_tasks  # type: ignore
            except Exception:
                should_use = False
            else:
                should_use = bool(should_use_cloud_tasks())

            if should_use:
                try:
                    # Build payload to send to /api/tasks/assemble; in dev this will route to a local
                    # thread fallback; in prod it uses Cloud Tasks HTTP to call back into the API.
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
                    }
                    task_info = enqueue_http_task("/api/tasks/assemble", payload)
                    # Store pseudo job id for visibility
                    try:
                        import json as _json
                        meta = {}
                        if getattr(ep, 'meta_json', None):
                            try:
                                meta = _json.loads(ep.meta_json or '{}')
                            except Exception:
                                meta = {}
                        meta['assembly_job_id'] = task_info.get('name') or 'cloud-task'
                        ep.meta_json = _json.dumps(meta)
                        session.add(ep)
                        session.commit()
                        session.refresh(ep)
                    except Exception:
                        session.rollback()
                    return {"mode": "cloud-task", "job_id": task_info.get("name", "cloud-task"), "episode_id": str(ep.id)}
                except Exception:
                    # If Cloud Tasks path fails, continue to Celery queue path as a secondary option
                    pass

        # Celery path (default)
        # Attempt to enqueue on Celery broker. If the broker is unreachable or
        # misconfigured, gracefully fall back to inline execution so the request
        # does not hang in production.
        if create_podcast_episode is None:
            inline_result = _run_inline_fallback(
                episode_id=ep.id,
                template_id=template_id,
                main_content_filename=main_content_filename,
                output_filename=output_filename,
                tts_values=tts_values or {},
                episode_details=episode_details or {},
                user_id=getattr(current_user, "id", None),
                podcast_id=getattr(ep, "podcast_id", None),
                intents=intents,
            )
            if inline_result:
                return inline_result
            _raise_worker_unavailable()

        async_result = None
        try:
            from typing import Any as _Any, cast as _cast

            task_fn = _cast(_Any, create_podcast_episode)
            if not hasattr(task_fn, "delay"):
                raise AttributeError("task missing delay attribute")
            async_result = task_fn.delay(
                episode_id=str(ep.id),
                template_id=str(template_id),
                main_content_filename=str(main_content_filename),
                output_filename=str(output_filename),
                tts_values=tts_values or {},
                episode_details=episode_details or {},
                user_id=str(current_user.id),
                podcast_id=str(getattr(ep, 'podcast_id', '') or ''),
                intents=intents or None,
            )
        except Exception:
            logging.getLogger("assemble").warning(
                "[assemble] Celery broker unreachable -> running inline fallback",
                exc_info=True,
            )
            inline_result = _run_inline_fallback(
                episode_id=ep.id,
                template_id=template_id,
                main_content_filename=main_content_filename,
                output_filename=output_filename,
                tts_values=tts_values or {},
                episode_details=episode_details or {},
                user_id=getattr(current_user, "id", None),
                podcast_id=getattr(ep, "podcast_id", None),
                intents=intents,
            )
            if inline_result:
                return inline_result
        # Store job id in meta for diagnostics
        if async_result is not None:
            try:
                import json as _json
                meta = {}
                if getattr(ep, 'meta_json', None):
                    try:
                        meta = _json.loads(ep.meta_json or '{}')
                    except Exception:
                        meta = {}
                meta['assembly_job_id'] = async_result.id
                ep.meta_json = _json.dumps(meta)
                session.add(ep); session.commit(); session.refresh(ep)
            except Exception:
                session.rollback()

        # Automatic dev/local fallback (or explicit env) if no workers respond
        if auto_fallback:
            no_workers = False
            if celery_app is None:
                no_workers = True
            else:
                try:
                    ping = celery_app.control.ping(timeout=1)
                    if not ping:
                        no_workers = True
                except Exception:
                    no_workers = True
            if no_workers:
                logging.getLogger("assemble").warning(
                    "[assemble] No Celery workers detected -> running fallback inline"
                )
                inline_result = _run_inline_fallback(
                    episode_id=ep.id,
                    template_id=template_id,
                    main_content_filename=main_content_filename,
                    output_filename=output_filename,
                    tts_values=tts_values or {},
                    episode_details=episode_details or {},
                    user_id=getattr(current_user, "id", None),
                    podcast_id=getattr(ep, "podcast_id", None),
                    intents=intents,
                )
                if inline_result:
                    return inline_result
        if async_result is None:
            _raise_worker_unavailable()
        from typing import Any as _Any, cast as _cast

        _ar = _cast(_Any, async_result)
        return {"mode": "queued", "job_id": _ar.id, "episode_id": str(ep.id)}
