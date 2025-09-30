from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class MediaItemUpdate(BaseModel):
    friendly_name: Optional[str] = None
    trigger_keyword: Optional[str] = None


class MainContentItem(BaseModel):
    id: UUID
    filename: str
    friendly_name: Optional[str] = None
    created_at: datetime
    expires_at: Optional[datetime] = None
    transcript_ready: bool = False
    intents: Dict[str, Any] = Field(default_factory=dict)
    notify_pending: bool = False
    duration_seconds: Optional[float] = None


__all__ = ["MediaItemUpdate", "MainContentItem"]
