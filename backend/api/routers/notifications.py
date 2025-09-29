from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from ..core.database import get_session
from ..models.notification import Notification, NotificationPublic
from ..models.user import User
from api.routers.auth import get_current_user
from typing import List

router = APIRouter(prefix="/notifications", tags=["Notifications"])

@router.get("/", response_model=List[NotificationPublic])
async def list_notifications(current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    """Return recent notifications. Opportunistically purge read>1h old to keep table small."""
    from datetime import datetime, timedelta
    cutoff = datetime.utcnow() - timedelta(hours=1)
    # Lazy cleanup
    try:
        session.exec(
            select(Notification)  # dummy to ensure connection
        )
        old = session.exec(
            select(Notification).where(Notification.user_id == current_user.id, Notification.read_at != None, Notification.read_at < cutoff)  # noqa: E711
        ).all()
        if old:
            for o in old:
                session.delete(o)
            session.commit()
    except Exception:
        session.rollback()
    q = select(Notification).where(Notification.user_id == current_user.id).order_by(Notification.created_at.desc()).limit(50)
    rows = session.exec(q).all()
    return [NotificationPublic(**r.dict()) for r in rows]
@router.delete("/purge")
async def purge_old_read(current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    """Explicit purge endpoint (optional) to delete read notifications older than 1 hour."""
    from datetime import datetime, timedelta
    cutoff = datetime.utcnow() - timedelta(hours=1)
    q = select(Notification).where(Notification.user_id == current_user.id, Notification.read_at != None, Notification.read_at < cutoff)  # noqa: E711
    rows = session.exec(q).all()
    count = 0
    for r in rows:
        session.delete(r)
        count += 1
    if count:
        session.commit()
    return {"deleted": count}

@router.post("/{notification_id}/read")
async def mark_read(notification_id: str, current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    from uuid import UUID
    try:
        nid = UUID(str(notification_id))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid notification id")
    note = session.get(Notification, nid)
    if not note or note.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Not found")
    from datetime import datetime
    if not note.read_at:
        note.read_at = datetime.utcnow()
        session.add(note)
        session.commit()
    return {"ok": True, "id": str(note.id), "already_read": note.read_at is not None}

@router.post("/read-all")
async def mark_all_read(current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    from datetime import datetime
    q = select(Notification).where(Notification.user_id == current_user.id, Notification.read_at == None)  # noqa: E711
    rows = session.exec(q).all()
    count = 0
    for r in rows:
        r.read_at = datetime.utcnow()
        session.add(r)
        count += 1
    if count:
        session.commit()
    return {"updated": count}
