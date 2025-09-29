from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlmodel import Session, select

from api.core.database import get_session
from api.models.podcast import Episode, Podcast
from api.models.user import User

from .deps import get_current_admin_user

router = APIRouter()


@router.get("/podcasts", status_code=200)
def admin_list_podcasts(
    owner_email: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
):
    """List podcasts for admins with optional owner email filter and pagination."""
    del admin_user
    like = None
    count_stmt = select(func.count(Podcast.id)).select_from(Podcast)
    if owner_email:
        like = f"%{owner_email.strip()}%"
        count_stmt = count_stmt.join(User, Podcast.user_id == User.id)
    if like:
        try:
            count_stmt = count_stmt.where(User.email.ilike(like))
        except Exception:
            count_stmt = count_stmt.where(func.lower(User.email).like((owner_email or "").lower()))
    total = session.exec(count_stmt).one() or 0

    data_stmt = select(Podcast, User.email).join(User, Podcast.user_id == User.id)
    if like:
        data_stmt = data_stmt.where(User.email.ilike(like))
    try:
        data_stmt = data_stmt.order_by(Podcast.created_at.desc())
    except Exception:
        data_stmt = data_stmt.order_by(Podcast.id.desc())
    data_stmt = data_stmt.offset(offset).limit(limit)
    rows = session.exec(data_stmt).all()

    page_podcasts: List[Podcast] = []
    owner_map: Dict[str, str] = {}
    for row in rows:
        try:
            podcast, email = row
        except Exception:
            podcast = row[0]
            email = row[1]
        page_podcasts.append(podcast)
        owner_map[str(podcast.id)] = email

    ids = [pod.id for pod in page_podcasts]
    count_map: Dict[str, int] = {str(pid): 0 for pid in ids}
    last_map: Dict[str, Optional[datetime]] = {str(pid): None for pid in ids}
    if ids:
        episodes = session.exec(select(Episode).where(Episode.podcast_id.in_(ids))).all()
        for episode in episodes:
            pid = str(episode.podcast_id)
            if pid not in count_map:
                continue
            count_map[pid] += 1
            timestamp = getattr(episode, "processed_at", None) or getattr(episode, "created_at", None)
            current = last_map.get(pid)
            if timestamp and (current is None or timestamp > current):
                last_map[pid] = timestamp

    items = []
    for podcast in page_podcasts:
        pid = str(podcast.id)
        created_iso = None
        last_iso = None
        try:
            if getattr(podcast, "created_at", None):
                created_iso = podcast.created_at.isoformat()
        except Exception:
            created_iso = None
        try:
            latest = last_map.get(pid)
            last_iso = latest.isoformat() if latest else None
        except Exception:
            last_iso = None
        items.append(
            {
                "id": pid,
                "name": getattr(podcast, "name", None),
                "owner_email": owner_map.get(pid),
                "episode_count": int(count_map.get(pid, 0)),
                "created_at": created_iso,
                "last_episode_at": last_iso,
            }
        )

    return {"items": items, "total": int(total or 0), "limit": limit, "offset": offset}


__all__ = ["router"]
