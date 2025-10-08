import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlmodel import select

from api.core.database import get_session
from api.routers.auth import get_current_user
from api.models.user import User
from api.models.podcast import Episode
from api.core.paths import FINAL_DIR, MEDIA_DIR
from .common import _final_url_for
from pathlib import Path

log = logging.getLogger("ppp.episodes.edit")
router = APIRouter(tags=["episodes"])  # parent provides /episodes prefix

# In-memory placeholder for cut manifests until persisted (MVP)
_CUT_STATE: Dict[str, List[Dict[str, int]]] = {}

@router.get("/{episode_id}/edit-context")
async def get_edit_context(episode_id: str, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    # Normalize ID and enforce ownership
    try:
        from uuid import UUID as _UUID
        eid = _UUID(str(episode_id))
    except Exception:
        raise HTTPException(status_code=404, detail="Episode not found")
    try:
        ep = session.execute(select(Episode).where(Episode.id == eid, Episode.user_id == current_user.id)).scalars().first()
    except Exception:
        ep = None
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")

    duration_ms = getattr(ep, 'duration_ms', None)
    # Resolve playback URL similar to list endpoint: prefer remote stream if linked, else local final audio if present
    playback_url = None
    playback_type = 'none'
    final_audio_exists = False
    try:
        fa = getattr(ep, 'final_audio_path', None)
        if fa:
            base = Path(str(fa)).name
            candidates = []
            try:
                candidates.append((FINAL_DIR / base).resolve())
            except Exception:
                candidates.append(FINAL_DIR / base)
            candidates.append(MEDIA_DIR / base)
            found = next((c for c in candidates if c.is_file()), None)
            if found is not None:
                final_audio_exists = True
                playback_url = _final_url_for(fa)
                playback_type = 'local'
        if not playback_url:
            spk_id = getattr(ep, 'spreaker_episode_id', None)
            if spk_id:
                playback_url = f"https://api.spreaker.com/v2/episodes/{spk_id}/play"
                playback_type = 'stream'
    except Exception:
        pass
    transcript_segments = []  # placeholder: would load from transcript store
    existing_cuts = _CUT_STATE.get(str(ep.id), [])
    flubber_keyword = 'flubber'
    flubber_detected = False  # server-side detection TBD

    # CRITICAL: Ensure audio_url is absolute for frontend waveform
    if playback_url and playback_type == 'local' and not playback_url.startswith('http'):
        # Make it absolute if relative
        if not playback_url.startswith('/'):
            playback_url = f"/{playback_url}"

    return {
        "episode_id": str(ep.id),
        "duration_ms": duration_ms,
        "flubber_keyword": flubber_keyword,
        "flubber_detected": flubber_detected,
        "transcript_segments": transcript_segments,
        "existing_cuts": existing_cuts,
        "audio_url": playback_url,
        "playback_type": playback_type,
        "final_audio_exists": final_audio_exists,
    }

@router.post("/{episode_id}/manual-edit/preview")
async def manual_edit_preview(episode_id: str, payload: Dict[str, Any], session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    # Normalize ID and enforce ownership
    try:
        from uuid import UUID as _UUID
        eid = _UUID(str(episode_id))
    except Exception:
        raise HTTPException(status_code=404, detail="Episode not found")
    ep = session.execute(select(Episode).where(Episode.id == eid, Episode.user_id == current_user.id)).scalars().first()
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")
    # Ownership already enforced above

    cuts = payload.get('cuts') or []
    norm: List[Dict[str, int]] = []
    for c in cuts:
        try:
            s = int(c.get('start_ms'))
            e = int(c.get('end_ms'))
            if e > s and e - s >= 20:  # minimum 20ms sanity
                norm.append({"start_ms": s, "end_ms": e})
        except Exception:
            continue
    norm.sort(key=lambda x: x['start_ms'])
    # merge overlaps
    merged: List[Dict[str, int]] = []
    for c in norm:
        if not merged or c['start_ms'] > merged[-1]['end_ms']:
            merged.append(c)
        else:
            merged[-1]['end_ms'] = max(merged[-1]['end_ms'], c['end_ms'])

    total_removed = sum(c['end_ms'] - c['start_ms'] for c in merged)
    new_duration_ms = (getattr(ep, 'duration_ms', None) or 0) - total_removed if getattr(ep, 'duration_ms', None) else None
    # Placeholder transcript shifting logic
    transcript_preview = []

    return {
        "episode_id": str(ep.id),
        "cuts": merged,
        "new_duration_ms": new_duration_ms,
        "transcript_preview": transcript_preview,
        "time_shift_map": [],
    }

@router.post("/{episode_id}/manual-edit/commit", status_code=status.HTTP_202_ACCEPTED)
async def manual_edit_commit(episode_id: str, payload: Dict[str, Any], session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    # Normalize ID and enforce ownership
    try:
        from uuid import UUID as _UUID
        eid = _UUID(str(episode_id))
    except Exception:
        raise HTTPException(status_code=404, detail="Episode not found")
    ep = session.execute(select(Episode).where(Episode.id == eid, Episode.user_id == current_user.id)).scalars().first()
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")
    # Ownership already enforced above

    cuts = payload.get('cuts') or []
    _CUT_STATE[str(ep.id)] = cuts  # store for reference

    # Kick off background job to apply cuts
    try:
        from worker.tasks.audio import manual_cut_episode
        async_mode = False
        try:
            # If Celery runs eagerly in dev, this returns result immediately
            res = manual_cut_episode.delay(str(ep.id), cuts)
            async_mode = True
            try:
                # Poll quickly for dev-eager
                out = res.get(timeout=2)
                if isinstance(out, dict) and out.get('ok'):
                    # Refresh episode props
                    session.refresh(ep)
                    return {"episode_id": str(ep.id), "status": "done", "final_audio_path": getattr(ep, 'final_audio_path', None), "duration_ms": getattr(ep, 'duration_ms', None)}
            except Exception:
                pass
        except Exception:
            # Fallback: run inline (dev only)
            out = manual_cut_episode(str(ep.id), cuts)
            if isinstance(out, dict) and out.get('ok'):
                session.refresh(ep)
                # Clear stored UI cuts once applied
                _CUT_STATE[str(ep.id)] = []
                return {"episode_id": str(ep.id), "status": "done", "final_audio_path": getattr(ep, 'final_audio_path', None), "duration_ms": getattr(ep, 'duration_ms', None)}
        return {"episode_id": str(ep.id), "status": "queued"}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"cut job failed: {ex}")
