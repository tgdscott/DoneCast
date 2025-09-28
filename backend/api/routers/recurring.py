# api/routers/recurring.py
from datetime import datetime, timedelta, time as dt_time, timezone
import os
from typing import List, Optional, Set
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlmodel import select

from api.core.auth import get_current_user
from api.core.database import get_session
from api.models.podcast import Episode
from api.models.recurring import RecurringSchedule
from api.models.user import User

router = APIRouter(prefix="/recurring", tags=["recurring"])

# ===== Public (user-auth) endpoints you already had =====

class RecurringScheduleCreate(BaseModel):
    day_of_week: int = Field(ge=0, le=6)  # 0=Mon .. 6=Sun
    time_of_day: str  # "HH:MM"
    template_id: str
    podcast_id: Optional[str] = None
    title_prefix: Optional[str] = None
    description_prefix: Optional[str] = None
    enabled: bool = True
    advance_minutes: int = 60


class RecurringNextSlotResponse(BaseModel):
    schedule_id: str
    timezone: str
    next_publish_at: Optional[str] = None  # UTC ISO8601 (Z)
    next_publish_at_local: Optional[str] = None  # YYYY-MM-DDTHH:MM
    next_publish_date: Optional[str] = None
    next_publish_time: Optional[str] = None
    conflicts_skipped: int = 0


def _timezone_for_user(user: User) -> ZoneInfo:
    tz_name = getattr(user, "timezone", None)
    if tz_name:
        try:
            return ZoneInfo(str(tz_name))
        except Exception:
            pass
    return ZoneInfo("UTC")


def _parse_time_of_day(value: object) -> dt_time:
    if isinstance(value, dt_time):
        return value
    text = str(value).strip() if value is not None else ""
    if not text:
        raise ValueError("time_of_day is required")
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    raise ValueError(f"Invalid time_of_day format: {value!r}")


def _scheduled_local_keys(session: Session, user_id, tz: ZoneInfo) -> Set[str]:
    """Return a set of YYYY-MM-DDTHH:MM strings already reserved by scheduled episodes."""

    now_utc = datetime.now(timezone.utc)
    try:
        episodes = session.exec(
            select(Episode)
            .where(Episode.user_id == user_id)
            .where(Episode.publish_at != None)  # noqa: E711
            .where(Episode.publish_at > now_utc)
        ).all()
    except Exception:
        episodes = []

    reserved: Set[str] = set()
    for ep in episodes:
        pub_dt = getattr(ep, "publish_at", None)
        if not pub_dt:
            continue
        try:
            if pub_dt.tzinfo is None or pub_dt.tzinfo.utcoffset(pub_dt) is None:
                pub_dt = pub_dt.replace(tzinfo=timezone.utc)
            local_dt = pub_dt.astimezone(tz)
            reserved.add(local_dt.strftime("%Y-%m-%dT%H:%M"))
        except Exception:
            continue
    return reserved


def _compute_next_occurrence(
    schedule: RecurringSchedule,
    tz: ZoneInfo,
    reserved: Set[str],
) -> Optional[dict]:
    try:
        day = int(schedule.day_of_week)
    except Exception:
        return None

    try:
        base_time = _parse_time_of_day(schedule.time_of_day)
    except ValueError:
        return None

    now_local = datetime.now(tz)
    days_ahead = (day - now_local.weekday()) % 7
    candidate_date = (now_local + timedelta(days=days_ahead)).date()
    candidate = datetime.combine(candidate_date, base_time, tz)
    if candidate <= now_local:
        candidate += timedelta(days=7)

    conflicts = 0
    for _ in range(520):  # ~10 years of weekly recurrences
        key = candidate.strftime("%Y-%m-%dT%H:%M")
        if key not in reserved:
            utc_iso = candidate.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            return {
                "utc_iso": utc_iso,
                "local_iso": key,
                "local_date": candidate.strftime("%Y-%m-%d"),
                "local_time": candidate.strftime("%H:%M"),
                "conflicts": conflicts,
            }
        candidate += timedelta(days=7)
        conflicts += 1
    return None

# In-memory store for demo (replace with DB in prod)
RECURRING_SCHEDULES: List[RecurringSchedule] = []

@router.get("/schedules", response_model=List[RecurringSchedule])
def list_schedules(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    tz = _timezone_for_user(current_user)
    tz_name = getattr(tz, "key", "UTC")
    reserved = _scheduled_local_keys(session, current_user.id, tz)

    results: List[RecurringSchedule] = []
    for schedule in RECURRING_SCHEDULES:
        if schedule.user_id != current_user.id:
            continue
        enriched = schedule.copy()
        enriched.timezone = tz_name
        info = _compute_next_occurrence(schedule, tz, reserved)
        if info:
            enriched.next_scheduled = info["utc_iso"]
            enriched.next_scheduled_local = info["local_iso"]
            enriched.next_scheduled_date = info["local_date"]
            enriched.next_scheduled_time = info["local_time"]
        results.append(enriched)
    return results

@router.post("/schedules", response_model=RecurringSchedule)
def create_schedule(
    rec_in: RecurringScheduleCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    try:
        parsed_time = _parse_time_of_day(rec_in.time_of_day)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    rec = RecurringSchedule(
        id=f"rec-{len(RECURRING_SCHEDULES)+1}",
        user_id=current_user.id,
        day_of_week=rec_in.day_of_week,
        time_of_day=parsed_time,
        template_id=rec_in.template_id,
        podcast_id=rec_in.podcast_id,
        title_prefix=rec_in.title_prefix,
        description_prefix=rec_in.description_prefix,
        enabled=rec_in.enabled,
        advance_minutes=rec_in.advance_minutes,
    )
    RECURRING_SCHEDULES.append(rec)

    tz = _timezone_for_user(current_user)
    tz_name = getattr(tz, "key", "UTC")
    reserved = _scheduled_local_keys(session, current_user.id, tz)
    info = _compute_next_occurrence(rec, tz, reserved)
    if info:
        rec.next_scheduled = info["utc_iso"]
        rec.next_scheduled_local = info["local_iso"]
        rec.next_scheduled_date = info["local_date"]
        rec.next_scheduled_time = info["local_time"]
    rec.timezone = tz_name
    return rec


@router.get("/schedules/{rec_id}/next", response_model=RecurringNextSlotResponse)
def get_next_schedule_slot(
    rec_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    schedule = next(
        (r for r in RECURRING_SCHEDULES if r.id == rec_id and r.user_id == current_user.id),
        None,
    )
    if not schedule:
        raise HTTPException(status_code=404, detail="Not found")

    tz = _timezone_for_user(current_user)
    tz_name = getattr(tz, "key", "UTC")
    reserved = _scheduled_local_keys(session, current_user.id, tz)
    info = _compute_next_occurrence(schedule, tz, reserved)
    if not info:
        return RecurringNextSlotResponse(schedule_id=rec_id, timezone=tz_name)

    return RecurringNextSlotResponse(
        schedule_id=rec_id,
        timezone=tz_name,
        next_publish_at=info["utc_iso"],
        next_publish_at_local=info["local_iso"],
        next_publish_date=info["local_date"],
        next_publish_time=info["local_time"],
        conflicts_skipped=info["conflicts"],
    )

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
