import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlmodel import select

from api.core.database import get_session
from api.core.auth import get_current_user
from api.models.user import User
from api.models.podcast import Episode
from api.core.paths import FINAL_DIR
from pathlib import Path

log = logging.getLogger("ppp.episodes.edit")
router = APIRouter(tags=["episodes"])  # parent provides /episodes prefix

# In-memory placeholder for cut manifests until persisted (MVP)
_CUT_STATE: Dict[str, List[Dict[str, int]]] = {}

@router.get("/{episode_id}/edit-context")
async def get_edit_context(episode_id: str, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    ep = session.execute(select(Episode).where(Episode.id == episode_id)).scalars().first()
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")
    # Basic ownership / access (admin or owner). Adjust as needed.
    if not (current_user.is_admin or getattr(ep, 'user_id', None) == current_user.id):
        raise HTTPException(status_code=403, detail="Forbidden")

    duration_ms = getattr(ep, 'duration_ms', None)
    transcript_segments = []  # placeholder: would load from transcript store
    existing_cuts = _CUT_STATE.get(str(ep.id), [])
    flubber_keyword = 'flubber'
    flubber_detected = False  # server-side detection TBD

    return {
        "episode_id": str(ep.id),
        "duration_ms": duration_ms,
        "flubber_keyword": flubber_keyword,
        "flubber_detected": flubber_detected,
        "transcript_segments": transcript_segments,
        "existing_cuts": existing_cuts,
    }

@router.post("/{episode_id}/manual-edit/preview")
async def manual_edit_preview(episode_id: str, payload: Dict[str, Any], session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    ep = session.execute(select(Episode).where(Episode.id == episode_id)).scalars().first()
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")
    if not (current_user.is_admin or getattr(ep, 'user_id', None) == current_user.id):
        raise HTTPException(status_code=403, detail="Forbidden")

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
    ep = session.execute(select(Episode).where(Episode.id == episode_id)).scalars().first()
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")
    if not (current_user.is_admin or getattr(ep, 'user_id', None) == current_user.id):
        raise HTTPException(status_code=403, detail="Forbidden")

    cuts = payload.get('cuts') or []
    _CUT_STATE[str(ep.id)] = cuts  # store as-is for now

    # For MVP we just acknowledge and pretend async job queued
    return {"episode_id": str(ep.id), "status": "queued", "message": "Edit job accepted (MVP stub)."}
