from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class PodcastWebsiteStatus(str, Enum):
    """Lifecycle state for generated podcast websites."""

    draft = "draft"
    published = "published"
    archived = "archived"


class PodcastWebsite(SQLModel, table=True):
    """Website configuration generated for a podcast."""

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    podcast_id: UUID = Field(foreign_key="podcast.id", index=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    subdomain: str = Field(max_length=80, index=True, description="Subdomain portion without the base domain")
    custom_domain: Optional[str] = Field(default=None, max_length=255, index=True)
    status: PodcastWebsiteStatus = Field(default=PodcastWebsiteStatus.draft)
    layout_json: str = Field(default="{}", description="Serialized PodcastWebsiteContent payload")
    last_generated_at: Optional[datetime] = Field(default=None)
    last_published_at: Optional[datetime] = Field(default=None)
    prompt_log_path: Optional[str] = Field(default=None, description="Last GCS object path recorded for AI prompts")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("podcast_id", name="uq_podcast_website_podcast"),
        UniqueConstraint("subdomain", name="uq_podcast_website_subdomain"),
    )

    def parsed_layout(self) -> Dict[str, Any]:
        """Return the deserialized layout JSON."""

        try:
            data: Dict[str, Any] = json.loads(self.layout_json or "{}")
            if isinstance(data, dict):
                return data
            return {}
        except Exception:
            return {}

    def apply_layout(self, layout: Dict[str, Any]) -> None:
        """Update the stored layout JSON and timestamps."""

        self.layout_json = json.dumps(layout)
        now = datetime.utcnow()
        self.last_generated_at = now
        self.updated_at = now
