from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


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


class MediaTranscript(SQLModel, table=True):
    """Persist transcript metadata for uploaded media files across deployments."""

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    media_item_id: Optional[UUID] = Field(default=None, foreign_key="mediaitem.id", index=True)
    filename: str = Field(index=True)
    transcript_meta_json: str = Field(default="{}", description="Serialized transcript metadata for this upload")
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow, index=True)

    __table_args__ = (UniqueConstraint("filename", name="uq_media_transcript_filename"),)


__all__ = ["TranscriptionWatch", "MediaTranscript"]
