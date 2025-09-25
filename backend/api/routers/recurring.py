# api/routers/recurring.py
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, Field
from uuid import UUID
import os

from api.core.database import get_session
from api.core.auth import get_current_user
from api.models.user import User
from api.models.recurring import RecurringSchedule

router = APIRouter(prefix="/recurring", tags=["recurring"])

# ===== Public (user-auth) endpoints you already had =====

class RecurringScheduleCreate(BaseModel):
    day_of_week: int = Field(ge=0, le=6)  # 0=Mon .. 6=Sun
    time_of_day: str                      # "HH:MM"
    template_id: str
    podcast_id: Optional[str] = None
    title_prefix: Optional[str] = None
    description_prefix: Optional[str] = None
    enabled: bool = True
    advance_minutes: int = 60

# In-memory store for demo (replace with DB in prod)
RECURRING_SCHEDULES: List[RecurringSchedule] = []

@router.get("/schedules", response_model=List[RecurringSchedule])
def list_schedules(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    return [r for r in RECURRING_SCHEDULES if r.user_id == current_user.id]

@router.post("/schedules", response_model=RecurringSchedule)
def create_schedule(
    rec_in: RecurringScheduleCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    rec = RecurringSchedule(
        id=f"rec-{len(RECURRING_SCHEDULES)+1}",
        user_id=current_user.id,
        day_of_week=rec_in.day_of_week,
        time_of_day=rec_in.time_of_day,
        template_id=rec_in.template_id,
        podcast_id=rec_in.podcast_id,
        title_prefix=rec_in.title_prefix,
        description_prefix=rec_in.description_prefix,
        enabled=rec_in.enabled,
        advance_minutes=rec_in.advance_minutes,
        next_scheduled=None,
    )
    RECURRING_SCHEDULES.append(rec)
    return rec

@router.delete("/schedules/{rec_id}")
def delete_schedule(
    rec_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    global RECURRING_SCHEDULES
    before = len(RECURRING_SCHEDULES)
    RECURRING_SCHEDULES = [
        r for r in RECURRING_SCHEDULES
        if not (r.id == rec_id and r.user_id == current_user.id)
    ]
    if len(RECURRING_SCHEDULES) == before:
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}

# ===== Internal (Scheduler/Tasks) endpoint =====

TASKS_AUTH = os.getenv("TASKS_AUTH", "")

@router.post("/cleanup")
def cleanup(
    x_tasks_auth: str | None = Header(None),
    session: Session = Depends(get_session),
):
    # Simple header-based auth shared with Cloud Scheduler / Cloud Tasks
    if not TASKS_AUTH:
        raise HTTPException(status_code=503, detail="TASKS_AUTH not configured")
    if x_tasks_auth != TASKS_AUTH:
        raise HTTPException(status_code=401, detail="unauthorized")

    # TODO: implement your real cleanup (e.g., delete expired uploads, etc.)
    # For now, a safe no-op:
    return {"ok": True}
