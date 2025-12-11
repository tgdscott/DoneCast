"""Podcast-related models: Podcast, PodcastTemplate, and related schemas.

This module contains models specific to podcasts, including show metadata,
templates for episode assembly, and distribution tracking.
"""
from sqlmodel import SQLModel, Field, Column, Relationship
from sqlalchemy.orm import relationship
from typing import List, Optional, Literal, Union, TYPE_CHECKING
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects.postgresql import JSON

from .enums import PodcastType, DistributionStatus

if TYPE_CHECKING:
    from .user import User
    from .episode import Episode
    from .media import BackgroundMusicRule, SegmentTiming


# NOTE: We deliberately import these at runtime (not just TYPE_CHECKING) so that
# Pydantic/SQLModel can resolve the forward references without requiring a
# manual model_rebuild() call in application code. When the models all lived in
# a single module this happened implicitly; after the refactor into separate
# modules we need to ensure the types are imported before model creation.
from .media import BackgroundMusicRule, SegmentTiming
from .user import User


class PodcastBase(SQLModel):
    """Base podcast model with shared fields."""
    name: str
    description: Optional[str] = None
    # Legacy cover_path (may hold local filename or remote URL). Prefer remote_cover_url going forward.
    cover_path: Optional[str] = None
    # Deprecated: rss_url & rss_url_locked are derivable from spreaker_show_id; retained for backward compat until migration.
    rss_url: Optional[str] = Field(default=None, index=True)
    rss_url_locked: Optional[str] = Field(default=None, description="Canonical RSS feed URL from Spreaker (immutable once set – deprecated; compute instead)")
    # New: authoritative Spreaker-hosted cover image URL (set after upload or show fetch)
    remote_cover_url: Optional[str] = Field(default=None, description="Spreaker-hosted show cover URL (preferred reference)")
    podcast_type: Optional[PodcastType] = Field(default=None)
    language: Optional[str] = None
    copyright_line: Optional[str] = None
    owner_name: Optional[str] = None
    author_name: Optional[str] = None
    spreaker_show_id: Optional[str] = None
    contact_email: Optional[str] = None
    # iTunes/RSS settings
    is_explicit: bool = Field(default=False, description="Podcast contains explicit content (iTunes)")
    itunes_category: Optional[str] = Field(default="Technology", description="Primary iTunes category")
    category_id: Optional[str] = Field(default=None, description="Primary Apple Podcasts category id")
    category_2_id: Optional[str] = Field(default=None, description="Secondary Apple Podcasts category id")
    category_3_id: Optional[str] = Field(default=None, description="Tertiary Apple Podcasts category id")
    # Ownership & source provenance
    podcast_guid: Optional[str] = Field(default=None, index=True, description="podcast:guid from RSS feed")
    feed_url_canonical: Optional[str] = Field(default=None, description="Final fetched URL after redirects")
    verification_method: Optional[str] = Field(default=None, description="email|dns when ownership verified")
    verified_at: Optional[datetime] = Field(default=None)
    # Friendly URL slug for public-facing URLs (RSS feeds, websites, etc.)
    slug: Optional[str] = Field(default=None, index=True, unique=True, max_length=100, description="URL-friendly slug for public links (e.g., 'my-awesome-podcast')")
    # Speaker identification settings
    has_guests: bool = Field(default=False, description="This podcast regularly features guests")
    speaker_intros: Optional[dict] = Field(default=None, sa_column=Column(JSON), description="Voice intro files for speaker identification - format: {'hosts': [{'name': 'Scott', 'gcs_path': 'gs://...', 'duration_ms': 2000}]}")
    guest_library: Optional[list] = Field(default=None, sa_column=Column(JSON), description="Reusable guest library - format: [{'id': 'uuid', 'name': 'Guest Name', 'gcs_path': 'gs://...', 'duration_ms': 2000, 'last_used': 'iso-date'}]")
    # Format selection from onboarding (for demographic purposes)
    format: Optional[str] = Field(default=None, description="Podcast format selected during onboarding: solo, interview, cohost, panel, narrative")


class Podcast(PodcastBase, table=True):
    """Main podcast (show) model with relationship to episodes."""
    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    user_id: UUID = Field(foreign_key="user.id")
    user: Optional[User] = Relationship(sa_relationship=relationship("User"))

    episodes: List["Episode"] = Relationship(back_populates="podcast", sa_relationship_kwargs={"cascade": "all, delete-orphan"})

    @property
    def rss_feed_url(self) -> Optional[str]:
        """
        Deterministic RSS feed URL for this podcast.
        
        ALWAYS uses production domain (donecast.com) for OP3 analytics compatibility.
        Uses slug if available, otherwise falls back to podcast ID.
        """
        # Get identifier (prefer slug over ID)
        identifier = getattr(self, 'slug', None) or str(self.id)
        
        # ALWAYS use production domain (hardcoded for OP3 analytics)
        return f"https://donecast.com/rss/{identifier}/feed.xml"

    @property
    def preferred_cover_url(self) -> Optional[str]:
        """Preferred cover image URL for this podcast (remote if available, else legacy cover_path)."""
        return getattr(self, 'remote_cover_url', None) or getattr(self, 'cover_path', None)


class PodcastImportState(SQLModel, table=True):
    """Lightweight progress tracker for partial RSS imports."""
    podcast_id: UUID = Field(primary_key=True, foreign_key="podcast.id")
    user_id: UUID = Field(foreign_key="user.id")
    source: Optional[str] = Field(
        default=None,
        description="Heuristic source label for the last RSS import (spreaker|external)",
    )
    feed_total: Optional[int] = Field(default=None, description="Total items detected in the feed during the last import")
    imported_count: int = Field(default=0, description="How many items were created during the preview import")
    needs_full_import: bool = Field(
        default=False,
        description="True when additional episodes remain to be recovered after the preview import",
    )
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Timestamp of the most recent import snapshot")


class PodcastDistributionStatus(SQLModel, table=True):
    """User-managed checklist items for submitting shows to external platforms."""
    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    podcast_id: UUID = Field(foreign_key="podcast.id", index=True)
    platform_key: str = Field(index=True, max_length=64, description="Stable key for the distribution platform")
    status: DistributionStatus = Field(default=DistributionStatus.not_started)
    notes: Optional[str] = Field(default=None, description="User-provided notes or reminders for this destination")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("podcast_id", "platform_key", name="uq_distribution_platform"),
    )

    def mark_status(self, new_status: DistributionStatus, notes: Optional[str] = None) -> None:
        """Update distribution status and optional notes."""
        self.status = new_status
        self.updated_at = datetime.utcnow()
        if notes is not None:
            cleaned = notes.strip()
            self.notes = cleaned or None


# Template-related models (for episode assembly)

class StaticSegmentSource(SQLModel):
    """Static audio file segment source."""
    source_type: Literal["static"] = "static"
    filename: str


class AIGeneratedSegmentSource(SQLModel):
    """AI-generated audio segment source."""
    source_type: Literal["ai_generated"] = "ai_generated"
    prompt: str
    voice_id: str = "19B4gjtpL5m876wS3Dfg"


class TTSSegmentSource(SQLModel):
    """Text-to-speech segment source."""
    source_type: Literal["tts"] = "tts"
    # For per-episode prompts, we only store a short label/placeholder in the template.
    # Keep legacy "script" for backward compatibility (old templates may have inline script).
    script: str = ""
    # Optional human-friendly label shown during episode creation (preferred going forward).
    text_prompt: Optional[str] = None
    # Default voice for this segment (optional)
    voice_id: str = "19B4gjtpL5m876wS3Dfg"


class TemplateSegment(SQLModel):
    """Segment definition within a podcast template."""
    id: UUID = Field(default_factory=uuid4)
    segment_type: Literal["intro", "outro", "commercial", "sound_effect", "transition", "content"]
    source: Union[StaticSegmentSource, AIGeneratedSegmentSource, TTSSegmentSource]


class PodcastTemplateCreate(SQLModel):
    """Schema for creating a new podcast template (Pydantic model, not a table)."""
    name: str
    segments: List[TemplateSegment]
    background_music_rules: List[BackgroundMusicRule] = Field(default_factory=list)
    timing: SegmentTiming = Field(default_factory=SegmentTiming)
    podcast_id: Optional[UUID] = None  # Associate template with a specific podcast/show
    # Optional: default ElevenLabs voice to seed per-episode TTS segments
    default_elevenlabs_voice_id: Optional[str] = None
    # Optional: default Intern voice for spoken command detection
    default_intern_voice_id: Optional[str] = None
    
    # AI settings for auto-suggestions in UI
    class AITemplateSettings(SQLModel):
        auto_fill_ai: bool = True
        title_instructions: Optional[str] = None
        notes_instructions: Optional[str] = None
        tags_instructions: Optional[str] = None
        tags_always_include: List[str] = []
    
    # Allow templates to opt out of automatic tag generation (persisted in ai_settings_json)
    auto_generate_tags: bool = True
    ai_settings: AITemplateSettings = Field(default_factory=AITemplateSettings)
    # New: allow disabling a template without deleting it
    is_active: bool = True
    
    # Episode length management settings (all values in seconds)
    soft_min_length_seconds: Optional[int] = Field(default=None, description="Soft minimum episode length target")
    soft_max_length_seconds: Optional[int] = Field(default=None, description="Soft maximum episode length target")
    hard_min_length_seconds: Optional[int] = Field(default=None, description="Hard minimum episode length limit")
    hard_max_length_seconds: Optional[int] = Field(default=None, description="Hard maximum episode length limit")
    length_management_enabled: bool = Field(default=False, description="Enable automatic length management")


class PodcastTemplate(SQLModel, table=True):
    """Reusable podcast template for episode assembly."""
    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    name: str
    user_id: UUID = Field(foreign_key="user.id")
    user: Optional[User] = Relationship(back_populates="templates", sa_relationship=relationship("User"))
    podcast_id: Optional[UUID] = Field(default=None, foreign_key="podcast.id")
    segments_json: str = Field(default="[]")
    background_music_rules_json: str = Field(default="[]")
    timing_json: str = Field(default_factory=lambda: SegmentTiming().model_dump_json())
    # New: JSON blob to hold AI settings
    ai_settings_json: str = Field(default_factory=lambda: PodcastTemplateCreate.AITemplateSettings().model_dump_json())
    # New: Active status toggle
    is_active: bool = Field(default=True)
    # New: default voice id for per-episode TTS segments
    default_elevenlabs_voice_id: Optional[str] = Field(default=None)
    # New: default voice id for Intern command detection
    default_intern_voice_id: Optional[str] = Field(default=None)
    
    # Episode length management settings
    soft_min_length_seconds: Optional[int] = Field(default=None)
    soft_max_length_seconds: Optional[int] = Field(default=None)
    hard_min_length_seconds: Optional[int] = Field(default=None)
    hard_max_length_seconds: Optional[int] = Field(default=None)
    length_management_enabled: bool = Field(default=False)

    episodes: List["Episode"] = Relationship(back_populates="template")


class PodcastTemplatePublic(PodcastTemplateCreate):
    """Public-facing podcast template schema with ID fields."""
    id: UUID
    user_id: UUID
    podcast_id: Optional[UUID] = None


# Resolve forward references now that dependent modules are imported.
_ns = globals().copy()
_ns.update({
    'User': User,
})
PodcastBase.model_rebuild(_types_namespace=_ns)
Podcast.model_rebuild(_types_namespace=_ns)
PodcastImportState.model_rebuild(_types_namespace=_ns)
PodcastDistributionStatus.model_rebuild(_types_namespace=_ns)
PodcastTemplateCreate.model_rebuild(_types_namespace=_ns)
PodcastTemplate.model_rebuild(_types_namespace=_ns)
PodcastTemplatePublic.model_rebuild(_types_namespace=_ns)
