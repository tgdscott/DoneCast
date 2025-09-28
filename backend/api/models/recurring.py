from datetime import datetime, time
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Column, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel


class RecurringScheduleBase(SQLModel):
    """Common fields shared by recurring schedule variants."""

    day_of_week: int = Field(ge=0, le=6, description="0=Monday .. 6=Sunday")

    time_of_day: time
    template_id: UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey("podcasttemplate.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    podcast_id: Optional[UUID] = Field(
        default=None,
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey("podcast.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    title_prefix: Optional[str] = None
    description_prefix: Optional[str] = None
    enabled: bool = Field(default=True)
    advance_minutes: int = Field(default=60)
    timezone: Optional[str] = Field(
        default=None,
        description="IANA timezone identifier used when computing next publish time",
        max_length=64,
    )


class RecurringSchedule(RecurringScheduleBase, table=True):
    """Database-backed recurring schedule linked to a template."""

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column_kwargs={"onupdate": datetime.utcnow},
    )


class RecurringScheduleRead(RecurringScheduleBase):
    """Public view of a recurring schedule enriched with next-occurrence metadata."""

    id: UUID
    user_id: UUID
    next_scheduled: Optional[str] = None
    next_scheduled_local: Optional[str] = None
    next_scheduled_date: Optional[str] = None
    next_scheduled_time: Optional[str] = None


class RecurringScheduleCreate(SQLModel):
    """Input payload for creating individual recurring schedule slots."""

    day_of_week: int = Field(ge=0, le=6)
    time_of_day: str
    template_id: UUID
    podcast_id: Optional[UUID] = None
    title_prefix: Optional[str] = None
    description_prefix: Optional[str] = None
    enabled: bool = True

    advance_minutes: int = 60  # How far in advance to create the draft
    next_scheduled: Optional[str] = None  # ISO8601 UTC string (Z suffix)
    next_scheduled_local: Optional[str] = None  # Local ISO string YYYY-MM-DDTHH:MM
    next_scheduled_date: Optional[str] = None  # YYYY-MM-DD in user's timezone
    next_scheduled_time: Optional[str] = None  # HH:MM in user's timezone
    timezone: Optional[str] = None

