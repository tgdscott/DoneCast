from __future__ import annotations

import os
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from api.core.constants import TIER_LIMITS
from api.models.podcast import Episode
from api.models.settings import AppSetting
from . import repo, dto
from worker.tasks import create_podcast_episode
from api.core.paths import MEDIA_DIR
from api.services.billing import usage as usage_svc
from math import ceil
import time


def _episodes_created_this_month(session: Session, user_id) -> int:
    from calendar import monthrange
    from datetime import datetime, timezone
    from sqlmodel import select
    from sqlalchemy import func

    now = datetime.now(timezone.utc)
    start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    try:
        q = select(func.count(Episode.id)).where(Episode.user_id == user_id)
        if hasattr(Episode, 'created_at'):
            q = q.where(Episode.created_at >= start)
        return session.exec(q).one()
    except Exception:
        return 0


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
    # Quota check (same logic as router but service-level)
    tier = getattr(current_user, 'tier', 'free')
    limits = TIER_LIMITS.get(tier, TIER_LIMITS['free'])
    max_eps = limits.get('max_episodes_month')
    if max_eps is not None:
        used = _episodes_created_this_month(session, current_user.id)
        if used >= max_eps:
            from fastapi import HTTPException
            raise HTTPException(status_code=402, detail="Monthly episode quota reached for your tier")

    # Prepare metadata and admin test-mode overrides
    ep_title = (episode_details.get("title") or output_filename or "").strip() or "Untitled Episode"
    ep_description = (episode_details.get("description") or "").strip()
    cover_image_path = episode_details.get("cover_image_path")
    sn_input = episode_details.get("season") or episode_details.get("season_number")
    en_input = episode_details.get("episodeNumber") or episode_details.get("episode_number")
    raw_tags = episode_details.get("tags")
    explicit_flag = bool(episode_details.get("explicit") or episode_details.get("is_explicit"))

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
            from pathlib import Path as _Path
            src_name = _Path(str(main_content_filename)).name
            src_path = MEDIA_DIR / src_name
            seconds = 0.0
            if src_path.is_file():
                try:
                    import subprocess, json as _json
                    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(src_path)]
                    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                    if proc.returncode == 0:
                        data = _json.loads(proc.stdout or '{}')
                        dur = float(data.get('format', {}).get('duration', 0))
                        if dur and dur > 0:
                            seconds = float(dur)
                except Exception:
                    pass
                if seconds <= 0:
                    try:
                        from pydub import AudioSegment as _AS
                        seg = _AS.from_file(src_path)
                        seconds = len(seg) / 1000.0
                    except Exception:
                        seconds = 0.0
            minutes = max(1, int(ceil(seconds / 60.0))) if seconds > 0 else 1
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
        result = create_podcast_episode(
            episode_id=str(ep.id),
            template_id=str(template_id),
            main_content_filename=str(main_content_filename),
            output_filename=str(output_filename),
            tts_values=tts_values or {},
            episode_details=episode_details or {},
            user_id=str(current_user.id),
            podcast_id=str(getattr(ep, 'podcast_id', '') or ''),
            intents=intents or None,
            skip_charge=True,
        )
        return {
            "mode": "eager-inline",
            "job_id": "eager-inline",
            "result": result,
            "episode_id": str(ep.id),
        }
    else:
        async_result = create_podcast_episode.delay(
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
        return {
            "mode": "queued",
            "job_id": async_result.id,
            "episode_id": str(ep.id),
        }
