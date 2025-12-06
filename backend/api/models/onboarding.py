from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import SQLModel, Field


class OnboardingSession(SQLModel, table=True):
    """Tracks objects created during a single onboarding run.

    Used so "Start Over" can delete everything created in that specific
    wizard session without touching any pre-existing podcasts or assets.
    """

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)

    # Primary podcast created for this onboarding run
    podcast_id: Optional[UUID] = Field(default=None, foreign_key="podcast.id")

    # Optional website created during onboarding for this podcast
    website_id: Optional[UUID] = Field(default=None, foreign_key="podcastwebsite.id")

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

