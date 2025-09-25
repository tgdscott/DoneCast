import os
import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlmodel import select

from api.core.database import get_session
from api.services.episodes import jobs as _svc_jobs
from api.models.podcast import Episode
from uuid import UUID as _UUID
from .common import _final_url_for, _cover_url_for, _status_value

logger = logging.getLogger("ppp.episodes.jobs")

router = APIRouter(tags=["episodes"])  # parent episodes router provides '/episodes' prefix


@router.get("/status/{job_id}")
def get_job_status(job_id: str, session: Session = Depends(get_session)):
    """Return job status and, if completed, the assembled episode info.

    Mirrors behavior of the existing endpoint in episodes_read.get_job_status.
    """
    raw = _svc_jobs.get_status(job_id)
    status_val = raw.get("raw_status", "PENDING")
    result = raw.get("raw_result")

    if status_val == "SUCCESS":
        ep_id = None
        if isinstance(result, dict):
            ep_id = result.get("episode_id")
        else:
            try:
                import json
                data = json.loads(str(result))
                ep_id = data.get("episode_id")
            except Exception:
                ep_id = None

        if not ep_id:
            return {"job_id": job_id, "status": "processed"}

        try:
            _uuid_obj = _UUID(str(ep_id))
        except Exception:
            _uuid_obj = None
        ep = session.exec(select(Episode).where(Episode.id == _uuid_obj)).first() if _uuid_obj else None
        if not ep:
            return {"job_id": job_id, "status": "processed"}

        cleanup_stats = None
        try:
            from pathlib import Path as _Path
            from api.core.paths import APP_ROOT
            log_path = APP_ROOT.parent / 'assembly_logs' / f"{ep.id}.log"
            if log_path.is_file():
                with open(log_path, 'r', encoding='utf-8') as lf:
                    for _ in range(50):
                        line = lf.readline()
                        if not line:
                            break
                        if '[CLEANUP_STATS]' in line:
                            parts = line.strip().split()
                            kv = {}
                            for p in parts:
                                if '=' in p:
                                    k, v = p.split('=', 1)
                                    if k in {'fillers_removed', 'pauses_compressed', 'time_saved_ms'}:
                                        try:
                                            kv[k] = int(v)
                                        except Exception:
                                            pass
                                    elif k in {'time_saved_pct'}:
                                        try:
                                            kv[k] = float(v)
                                        except Exception:
                                            pass
                                    elif k == 'filler_map':
                                        filler_map_idx = parts.index(p)
                                        filler_raw = ' '.join(parts[filler_map_idx:])
                                        filler_raw = filler_raw.split('=', 1)[1]
                                        kv['filler_map'] = filler_raw
                                        break
                            if kv:
                                cleanup_stats = kv
                            break
        except Exception:
            cleanup_stats = None

        assembled = {
            "id": str(ep.id),
            "title": ep.title,
            "description": ep.show_notes or "",
            "final_audio_url": _final_url_for(ep.final_audio_path),
            "cover_url": (_cover_url_for(getattr(ep, 'remote_cover_url', None)) or _cover_url_for(ep.cover_path)),
            "status": _status_value(ep.status),
        }
        base_resp = {"job_id": job_id, "status": "processed", "episode": assembled, "message": (result.get("message") if isinstance(result, dict) else None)}
        if cleanup_stats:
            base_resp['cleanup_stats'] = cleanup_stats
        return base_resp

    if status_val in ("STARTED", "RETRY"):
        return {"job_id": job_id, "status": "processing"}

    if status_val == "PENDING":
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
            from sqlalchemy import text as _sa_text
            recent = session.exec(
                select(Episode)
                .where(Episode.processed_at >= cutoff)  # type: ignore[arg-type]
                .order_by(_sa_text("processed_at DESC"))
                .limit(10)
            ).all()
            for ep in recent:
                if getattr(ep, 'final_audio_path', None) and getattr(ep, 'status', None) in ("processed", "published"):
                    return {"job_id": job_id, "status": "processed", "episode": {
                        "id": str(ep.id),
                        "title": ep.title,
                        "description": ep.show_notes or "",
                        "final_audio_url": _final_url_for(ep.final_audio_path),
                        "cover_url": (_cover_url_for(getattr(ep, 'remote_cover_url', None)) or _cover_url_for(ep.cover_path)),
                        "status": _status_value(ep.status),
                    }}
        except Exception:
            pass
        return {"job_id": job_id, "status": "queued"}

    err_text = None
    if isinstance(result, dict):
        err_text = result.get("error") or result.get("detail")
    if not err_text:
        err_text = str(result)
    return {"job_id": job_id, "status": "error", "error": err_text}
