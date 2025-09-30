from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import SQLModel, Field


class TranscriptionWatch(SQLModel, table=True):
    """Track users requesting notification when an upload is processed."""

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    filename: str = Field(index=True)
    friendly_name: Optional[str] = None
    notify_email: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    notified_at: Optional[datetime] = Field(default=None, index=True)
    last_status: Optional[str] = None


__all__ = ["TranscriptionWatch"]
