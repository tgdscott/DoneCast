from datetime import datetime, timedelta, time as dt_time, timezone
import os
from typing import Dict, List, Optional, Sequence, Set
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from api.routers.auth import get_current_user
from api.core.database import get_session
from api.models.podcast import Episode, PodcastTemplate
from api.models.recurring import (
    RecurringSchedule,
    RecurringScheduleRead,
)
from api.models.user import User

router = APIRouter(prefix="/recurring", tags=["recurring"])

MAX_WEEKS_LOOKAHEAD = 520  # ~10 years of weekly recurrences


class RecurringNextSlotResponse(BaseModel):
    schedule_id: Optional[UUID] = None
    template_id: Optional[UUID] = None
    timezone: str
    next_publish_at: Optional[str] = None  # UTC ISO8601 (Z)
    next_publish_at_local: Optional[str] = None  # YYYY-MM-DDTHH:MM
    next_publish_date: Optional[str] = None
    next_publish_time: Optional[str] = None
    conflicts_skipped: int = 0


class ScheduleSlotPayload(BaseModel):
    id: Optional[UUID] = None
    day_of_week: int = Field(ge=0, le=6)
    time_of_day: str  # "HH:MM"
    enabled: bool = True
    advance_minutes: int = 60
    timezone: Optional[str] = None


class TemplateSchedulesResponse(BaseModel):
    template_id: UUID
    timezone: Optional[str] = None
    schedules: List[RecurringScheduleRead] = Field(default_factory=list)


class TemplateSchedulesRequest(BaseModel):
    timezone: Optional[str] = None
    schedules: List[ScheduleSlotPayload] = Field(default_factory=list)


def _safe_timezone(name: Optional[str]) -> Optional[ZoneInfo]:
    if not name:
        return None
    try:
        return ZoneInfo(str(name))
    except Exception:
        return None


def _timezone_name(tz: ZoneInfo) -> str:
    return getattr(tz, "key", None) or getattr(tz, "zone", None) or str(tz)


def _timezone_for_user(user: User) -> ZoneInfo:
    tz = _safe_timezone(getattr(user, "timezone", None))
    return tz or ZoneInfo("UTC")


def _timezone_for_schedule(schedule: RecurringSchedule, user: User) -> ZoneInfo:
    tz = _safe_timezone(getattr(schedule, "timezone", None))
    return tz or _timezone_for_user(user)


def _parse_time_of_day(value: object) -> dt_time:
    if isinstance(value, dt_time):
        return value
    text = str(value).strip() if value is not None else ""
    if not text:
        raise ValueError("time_of_day is required")
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).time().replace(second=0, microsecond=0)
        except ValueError:
            continue
    raise ValueError(f"Invalid time_of_day format: {value!r}")


def _fetch_upcoming_publish_times(session: Session, user_id: UUID) -> List[datetime]:
    now_utc = datetime.now(timezone.utc)
    from sqlalchemy import text as _sa_text
    stmt = (
        select(Episode)
        .where(Episode.user_id == user_id)
        .where(_sa_text("publish_at IS NOT NULL"))
        .where(Episode.publish_at > now_utc)  # type: ignore[operator]
    )
    try:
        episodes = session.exec(stmt).all()
    except Exception:
        return []

    results: List[datetime] = []
    for ep in episodes:
        pub_dt = getattr(ep, "publish_at", None)
        if not pub_dt:
            continue
        try:
            if pub_dt.tzinfo is None or pub_dt.tzinfo.utcoffset(pub_dt) is None:
                pub_dt = pub_dt.replace(tzinfo=timezone.utc)
            results.append(pub_dt.astimezone(timezone.utc))
        except Exception:
            continue
    return results


def _scheduled_local_keys(episodes: Sequence[datetime], tz: ZoneInfo) -> Set[str]:
    reserved: Set[str] = set()
    for dt in episodes:
        try:
            local_dt = dt.astimezone(tz)
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
        day = int(getattr(schedule, "day_of_week", 0))
    except Exception:
        return None
    try:
        base_time = _parse_time_of_day(getattr(schedule, "time_of_day", None))
    except ValueError:
        return None

    now_local = datetime.now(tz)
    days_ahead = (day - now_local.weekday()) % 7
    candidate_date = (now_local + timedelta(days=days_ahead)).date()
    candidate = datetime.combine(candidate_date, base_time, tz)
    if candidate <= now_local:
        candidate += timedelta(days=7)

    conflicts = 0
    for _ in range(MAX_WEEKS_LOOKAHEAD):
        key = candidate.strftime("%Y-%m-%dT%H:%M")
        if key not in reserved:
            utc_dt = candidate.astimezone(timezone.utc)
            return {
                "utc_iso": utc_dt.isoformat().replace("+00:00", "Z"),
                "local_iso": key,
                "local_date": candidate.strftime("%Y-%m-%d"),
                "local_time": candidate.strftime("%H:%M"),
                "conflicts": conflicts,
            }
        candidate += timedelta(days=7)
        conflicts += 1
    return None


def _serialize_schedule(
    schedule: RecurringSchedule,
    tz: ZoneInfo,
    info: Optional[dict],
) -> RecurringScheduleRead:
    tz_name = getattr(schedule, "timezone", None) or _timezone_name(tz)
    data = RecurringScheduleRead(
        id=schedule.id,
        user_id=schedule.user_id,
        day_of_week=int(getattr(schedule, "day_of_week", 0)),
        time_of_day=_parse_time_of_day(getattr(schedule, "time_of_day", None)),
        template_id=schedule.template_id,
        podcast_id=getattr(schedule, "podcast_id", None),
        title_prefix=getattr(schedule, "title_prefix", None),
        description_prefix=getattr(schedule, "description_prefix", None),
        enabled=bool(getattr(schedule, "enabled", True)),
        advance_minutes=int(getattr(schedule, "advance_minutes", 60) or 60),
        timezone=tz_name,
    )
    if info:
        data.next_scheduled = info["utc_iso"]
        data.next_scheduled_local = info["local_iso"]
        data.next_scheduled_date = info["local_date"]
        data.next_scheduled_time = info["local_time"]
    return data


def _assert_template_access(
    session: Session,
    template_id: UUID,
    user_id: UUID,
) -> PodcastTemplate:
    template = session.get(PodcastTemplate, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    if str(template.user_id) != str(user_id):
        # Allow access if it's a known system template
        if str(template.id) not in SYSTEM_TEMPLATES:
            raise HTTPException(status_code=403, detail="Not authorized to modify this template")
    return template


def _normalize_timezone_choice(value: Optional[str], user: User) -> str:
    candidates = [value, getattr(user, "timezone", None), "UTC"]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            ZoneInfo(str(candidate))
            return str(candidate)
        except Exception:
            continue
    return "UTC"


@router.delete("/schedules/{rec_id}")
def delete_schedule(
    rec_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    schedule = session.get(RecurringSchedule, rec_id)
    if not schedule or schedule.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Not found")
    session.delete(schedule)
    session.commit()
    return {"ok": True}


@router.get("/templates/{template_id}/schedules", response_model=TemplateSchedulesResponse)
def list_template_schedules(
    template_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _assert_template_access(session, template_id, current_user.id)
    stmt = (
        select(RecurringSchedule)
        .where(RecurringSchedule.user_id == current_user.id)
        .where(RecurringSchedule.template_id == template_id)
    )
    schedules = session.exec(stmt).all()
    upcoming = _fetch_upcoming_publish_times(session, current_user.id)
    reserved_cache: Dict[str, Set[str]] = {}
    items: List[RecurringScheduleRead] = []
    for schedule in schedules:
        tz = _timezone_for_schedule(schedule, current_user)
        tz_key = _timezone_name(tz)
        if tz_key not in reserved_cache:
            reserved_cache[tz_key] = _scheduled_local_keys(upcoming, tz)
        info = _compute_next_occurrence(schedule, tz, reserved_cache[tz_key])
        items.append(_serialize_schedule(schedule, tz, info))

    preferred_timezone = next((s.timezone for s in schedules if s.timezone), None)
    if not preferred_timezone:
        preferred_timezone = getattr(current_user, "timezone", None)
    return TemplateSchedulesResponse(
        template_id=template_id,
        timezone=preferred_timezone,
        schedules=items,
    )


@router.put("/templates/{template_id}/schedules", response_model=TemplateSchedulesResponse)
def replace_template_schedules(
    template_id: UUID,
    payload: TemplateSchedulesRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    template = _assert_template_access(session, template_id, current_user.id)
    stmt = (
        select(RecurringSchedule)
        .where(RecurringSchedule.user_id == current_user.id)
        .where(RecurringSchedule.template_id == template_id)
    )
    existing = {schedule.id: schedule for schedule in session.exec(stmt).all()}
    keep_ids: Set[UUID] = set()
    default_timezone = _normalize_timezone_choice(payload.timezone, current_user)

    for slot in payload.schedules:
        try:
            parsed_time = _parse_time_of_day(slot.time_of_day)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        slot_tz = _normalize_timezone_choice(slot.timezone, current_user) if slot.timezone else default_timezone

        if slot.id and slot.id in existing:
            schedule = existing[slot.id]
            schedule.day_of_week = slot.day_of_week
            schedule.time_of_day = parsed_time
            schedule.enabled = slot.enabled
            schedule.advance_minutes = slot.advance_minutes
            schedule.timezone = slot_tz
            keep_ids.add(schedule.id)
        else:
            schedule = RecurringSchedule(
                user_id=current_user.id,
                day_of_week=slot.day_of_week,
                time_of_day=parsed_time,
                template_id=template_id,
                podcast_id=getattr(template, "podcast_id", None),
                enabled=slot.enabled,
                advance_minutes=slot.advance_minutes,
                timezone=slot_tz,
            )
            session.add(schedule)
            session.flush()
            keep_ids.add(schedule.id)

    for schedule_id, schedule in existing.items():
        if schedule_id not in keep_ids:
            session.delete(schedule)
    session.commit()
    return list_template_schedules(template_id, session, current_user)


# Known system templates that should be publicly readable
SYSTEM_TEMPLATES = {
    "bfd659d9-8088-4019-aefb-c41ad1f4b58a"
}


@router.get("/templates/{template_id}/next", response_model=RecurringNextSlotResponse)
def get_template_next_slot(
    template_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _assert_template_access(session, template_id, current_user.id)
    stmt = (
        select(RecurringSchedule)
        .where(RecurringSchedule.user_id == current_user.id)
        .where(RecurringSchedule.template_id == template_id)
    )
    schedules = session.exec(stmt).all()
    if not schedules:
        tz_name = getattr(current_user, "timezone", None) or "UTC"
        return RecurringNextSlotResponse(template_id=template_id, timezone=tz_name)

    upcoming = _fetch_upcoming_publish_times(session, current_user.id)
    reserved_cache: Dict[str, Set[str]] = {}
    best_info: Optional[dict] = None
    best_schedule: Optional[RecurringSchedule] = None
    best_tz: Optional[ZoneInfo] = None

    for schedule in schedules:
        tz = _timezone_for_schedule(schedule, current_user)
        tz_key = _timezone_name(tz)
        if tz_key not in reserved_cache:
            reserved_cache[tz_key] = _scheduled_local_keys(upcoming, tz)
        info = _compute_next_occurrence(schedule, tz, reserved_cache[tz_key])
        if not info:
            continue
        # Compare by UTC ISO strings to find earliest slot
        if not best_info or info["utc_iso"] < best_info["utc_iso"]:
            best_info = info
            best_schedule = schedule
            best_tz = tz

    if not best_info or not best_schedule or not best_tz:
        tz_name = getattr(current_user, "timezone", None) or "UTC"
        return RecurringNextSlotResponse(template_id=template_id, timezone=tz_name)

    tz_name = getattr(best_schedule, "timezone", None) or _timezone_name(best_tz)
    return RecurringNextSlotResponse(
        schedule_id=best_schedule.id,
        template_id=template_id,
        timezone=tz_name,
        next_publish_at=best_info["utc_iso"],
        next_publish_at_local=best_info["local_iso"],
        next_publish_date=best_info["local_date"],
        next_publish_time=best_info["local_time"],
        conflicts_skipped=best_info["conflicts"],
    )


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
