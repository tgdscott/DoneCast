from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import Column, Text, ForeignKey
from sqlalchemy.orm import Mapped, relationship
from sqlmodel import Field, SQLModel, Relationship


class WebsitePage(SQLModel, table=True):
    """A page within a podcast website. Each page has its own sections."""
    
    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    website_id: UUID = Field(foreign_key="podcastwebsite.id", index=True)
    title: str = Field(max_length=200, description="Page title (shown in navigation)")
    slug: str = Field(max_length=200, index=True, description="URL slug for this page")
    is_home: bool = Field(default=False, description="Whether this is the home page")
    order: int = Field(default=0, description="Display order in navigation")
    
    # Section-based architecture (same as website)
    sections_order: Optional[str] = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
        description="JSON array of section IDs in display order"
    )
    sections_config: Optional[str] = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
        description="JSON object mapping section ID to configuration"
    )
    sections_enabled: Optional[str] = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
        description="JSON object mapping section ID to enabled boolean"
    )
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationship
    website: Mapped[Optional["PodcastWebsite"]] = Relationship(
        back_populates="pages",
        sa_relationship=relationship("PodcastWebsite", back_populates="pages")
    )
    
    def get_sections_order(self) -> List[str]:
        """Return the ordered list of section IDs."""
        try:
            if self.sections_order:
                data = json.loads(self.sections_order)
                if isinstance(data, list):
                    return data
            return []
        except Exception:
            return []
    
    def set_sections_order(self, order: List[str]) -> None:
        """Set the section order."""
        self.sections_order = json.dumps(order)
        self.updated_at = datetime.utcnow()
    
    def get_sections_config(self) -> Dict[str, Dict[str, Any]]:
        """Return the section configurations."""
        try:
            if self.sections_config:
                data = json.loads(self.sections_config)
                if isinstance(data, dict):
                    return data
            return {}
        except Exception:
            return {}
    
    def set_sections_config(self, config: Dict[str, Dict[str, Any]]) -> None:
        """Set the section configurations."""
        self.sections_config = json.dumps(config)
        self.updated_at = datetime.utcnow()
    
    def get_sections_enabled(self) -> Dict[str, bool]:
        """Return the section enabled states."""
        try:
            if self.sections_enabled:
                data = json.loads(self.sections_enabled)
                if isinstance(data, dict):
                    return data
            return {}
        except Exception:
            return {}
    
    def set_sections_enabled(self, enabled: Dict[str, bool]) -> None:
        """Set the section enabled states."""
        self.sections_enabled = json.dumps(enabled)
        self.updated_at = datetime.utcnow()

