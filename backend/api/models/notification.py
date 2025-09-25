from sqlmodel import SQLModel, Field
from datetime import datetime
from uuid import UUID, uuid4
from typing import Optional


class Notification(SQLModel, table=True):
    """Simple user notification (e.g., billing upgrades)."""
    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    type: str = Field(default="info", index=True)
    title: str
    body: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    read_at: Optional[datetime] = Field(default=None, index=True)


class NotificationPublic(SQLModel):
    id: UUID
    type: str
    title: str
    body: Optional[str] = None
    created_at: datetime
    read_at: Optional[datetime] = None
