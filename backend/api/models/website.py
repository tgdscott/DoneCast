from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint, Column, Text
from sqlalchemy.orm import Mapped, relationship
from sqlmodel import Field, SQLModel, Relationship

# Import WebsitePage at runtime for SQLAlchemy relationship resolution  
from api.models.website_page import WebsitePage


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
    layout_json: str = Field(default="{}", description="Serialized PodcastWebsiteContent payload (legacy)")
    
    # Section-based architecture fields (added Oct 15, 2025)
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
    global_css: Optional[str] = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
        description="Custom CSS styles applied to the entire website"
    )
    
    last_generated_at: Optional[datetime] = Field(default=None)
    last_published_at: Optional[datetime] = Field(default=None)
    prompt_log_path: Optional[str] = Field(default=None, description="Last GCS object path recorded for AI prompts")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationship to pages
    pages: Mapped[list["WebsitePage"]] = Relationship(
        back_populates="website",
        sa_relationship=relationship("WebsitePage", back_populates="website")
    )

    __table_args__ = (
        UniqueConstraint("podcast_id", name="uq_podcast_website_podcast"),
        UniqueConstraint("subdomain", name="uq_podcast_website_subdomain"),
    )

    def parsed_layout(self) -> Dict[str, Any]:
        """Return the deserialized layout JSON (legacy)."""

        try:
            data: Dict[str, Any] = json.loads(self.layout_json or "{}")
            if isinstance(data, dict):
                return data
            return {}
        except Exception:
            return {}

    def apply_layout(self, layout: Dict[str, Any]) -> None:
        """Update the stored layout JSON and timestamps (legacy)."""

        self.layout_json = json.dumps(layout)
        now = datetime.utcnow()
        self.last_generated_at = now
        self.updated_at = now
    
    # --- Section-based methods ---
    
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
    
    def update_section_config(self, section_id: str, config: Dict[str, Any]) -> None:
        """Update configuration for a single section."""
        all_config = self.get_sections_config()
        all_config[section_id] = config
        self.set_sections_config(all_config)
    
    def toggle_section(self, section_id: str, enabled: bool) -> None:
        """Enable or disable a specific section."""
        all_enabled = self.get_sections_enabled()
        all_enabled[section_id] = enabled
        self.set_sections_enabled(all_enabled)
